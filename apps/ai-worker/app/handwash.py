"""WHO hand washing, checked once per wash at each sink.

A wash starts when the gesture model finds hands in a hand-wash zone and ends once no hands have been
seen there for the wash gap. The gesture read a few times a second settles when two of the last three
reads agree, and a step is done once it has been the settled gesture for the rule's minimum duration.
When the wash ends, a step that is checked but not done is missing. A step is checked only when the
model has a class for it and it is not skipped in the settings, so a step the model cannot see never
raises an alert.

None of the timings below has been measured on site footage yet. The reference model was only
checked on 40 still frames.
"""

from collections import Counter, deque
from dataclasses import dataclass, field

from app.scenes import WASH_STEPS

HANDWASH_CONDITION = "HANDWASH_STEPS_MISSING"
STEP_NAMES = {
    "palms": "Palm to palm",
    "backs": "Backs of hands",
    "interlaced": "Fingers interlaced",
    "fingers": "Backs of fingers",
    "thumbs": "Thumbs",
    "fingertips": "Fingertips",
}
# Hands out of view this long end the wash; HANDWASH_GAP_S sets it. In the site's sample videos the
# hands were never lost for more than 1.2 s during a wash, while two washes one after the other were
# 2.6-3.2 s apart. At 4 s those two ran together into one wash with the steps of both, and passed.
WASH_GAP_S = 2.5
# Hands seen for less than this are someone passing the sink, not a wash.
MIN_WASH_S = 3.0
# Thumbs is read right in 7 of 10 test frames. In a clip of those frames, 6 s of thumbs was credited
# 2.8-6.8 s with three of five votes, so a full wash could be reported missing it, and 4.2-5.4 s with
# two of three. Fingertips not done, after 6 s of thumbs, picked up 1.6-2.4 s, still short of 3 s.
VOTE_WINDOW = 3
VOTES_NEEDED = 2
# A stalled loop does not count as washing time.
MAX_READ_GAP_S = 1.0


@dataclass
class Wash:
    id: str
    started_at: float
    last_seen_at: float
    last_read_at: float
    seen_s: float = 0.0
    step_s: dict[str, float] = field(default_factory=dict)
    votes: deque = field(default_factory=lambda: deque(maxlen=VOTE_WINDOW))
    box: list[float] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    # The last frame with hands in view, for the incident snapshot.
    frame: object = None
    # The hands' 21 joints each, in frame pixels, for the overlay only.
    joints: list = field(default_factory=list)

    @property
    def confidence(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0.0


def missing_steps(wash: Wash, checked: set[str], min_step_s: float) -> list[str]:
    return [step for step in WASH_STEPS if step in checked and wash.step_s.get(step, 0.0) < min_step_s]


def wash_checks(wash: Wash, checked: set[str], min_step_s: float, finished: bool = False) -> list[dict]:
    """One check per checked step, numbered as on the WHO poster. Not done yet is unknown until the wash ends."""
    checks = []
    for number, step in enumerate(WASH_STEPS, start=1):
        if step not in checked:
            continue
        if wash.step_s.get(step, 0.0) >= min_step_s:
            state = "ok"
        else:
            state = "violation" if finished else "unknown"
        checks.append({"item": f"step{number}", "text": f"{number} {STEP_NAMES[step]}", "state": state})
    return checks


@dataclass
class WashTracker:
    """The wash under way at each hand-wash zone. Feed it one read per zone each time the model runs."""

    washes: dict[str, Wash] = field(default_factory=dict)
    gap_s: float = WASH_GAP_S

    def observe(self, zone_id: str, read: tuple[str, float, list[float]] | None, now: float, frame=None) -> Wash | None:
        """read is (step, score, box) for the hands in this zone, or None. Returns a wash that just ended."""
        wash = self.washes.get(zone_id)
        if read is None:
            if wash is None:
                return None
            wash.votes.append("")
            wash.last_read_at = now
            if now - wash.last_seen_at <= self.gap_s:
                return None
            self.washes.pop(zone_id)
            return wash if wash.seen_s >= MIN_WASH_S else None
        step, score, box = read
        if wash is None:
            # Seconds since the epoch: unique across worker restarts, so the backend never takes it for an earlier wash.
            wash = Wash(id=f"W{int(now) % 1000000}", started_at=now, last_seen_at=now, last_read_at=now)
            self.washes[zone_id] = wash
        elapsed = min(max(0.0, now - wash.last_read_at), MAX_READ_GAP_S)
        wash.votes.append(step)
        wash.seen_s += elapsed
        settled, count = Counter(wash.votes).most_common(1)[0]
        if settled and count >= VOTES_NEEDED:
            wash.step_s[settled] = wash.step_s.get(settled, 0.0) + elapsed
        wash.last_seen_at = wash.last_read_at = now
        wash.box = box
        wash.scores.append(score)
        wash.frame = frame
        return None

    def finish_all(self) -> list[tuple[str, Wash]]:
        """Ends every wash now, as (zone id, wash). Hands seen too briefly to be a wash are dropped."""
        ended = [(zone_id, wash) for zone_id, wash in self.washes.items() if wash.seen_s >= MIN_WASH_S]
        self.washes.clear()
        return ended

    def forget(self, zone_ids: set[str]) -> None:
        """Drops washes at zones no longer watched, such as when the rule is turned off."""
        for zone_id in set(self.washes) - zone_ids:
            self.washes.pop(zone_id)
