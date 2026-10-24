from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", protected_namespaces=())

    api_base_url: str = "http://backend:8000"
    internal_api_token: str = "poc-internal-token"
    ai_mode: str = "DEMO"
    ai_device: str = "cpu"
    model_path: str = "/models"
    default_ai_fps: int = 5
    worker_id: str = "worker-01"
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "safetyadmin"
    minio_secret_key: str = "safetyadmin123"
    minio_bucket: str = "safety-evidence"
    minio_secure: bool = False
    # PPE is read from each person's pixels. At 960x540 helmet and clothing reads on the workshop clip were clearly worse.
    frame_width: int = 1280
    frame_height: int = 720
    # Inference threads per camera. Cameras run in parallel, so a few threads each keeps them from fighting over cores.
    ai_threads: int = 2
    config_refresh_s: float = 1.0
    heartbeat_every_s: float = 0.5
    # How often each person's PPE is read again. ppe.onnx runs once per person crop, so not every frame.
    ppe_interval_s: float = 0.3
    # How often handwash.onnx reads the gesture at each sink. It takes about 70 ms on 2 threads.
    handwash_interval_s: float = 0.2
    # Hand-washing steps never checked, comma separated. The site's classifier, handwash_steps.onnx, reads all six.
    # With only the reference handwash.onnx set "fingers": it read backs of fingers as fingertips in 9 of 10
    # real test frames, so every wash would be reported missing it.
    handwash_skip_steps: str = ""
    # How much smaller the frame goes into handwash.onnx, for a camera closer to the sink than the reference.
    # On the site's sink, with hands a fifth of the frame wide, the model found hands in 21 of 170 reads at 1.0
    # and 135 at 0.7. With a 2.5 s wash gap, 0.6 passed the correct sample video and flagged the wrong one in
    # all six timings tried, for gaps from 2 to 3 s. The reference camera, hands a tenth of the frame wide, wants 1.0.
    handwash_scale: float = 0.6
    # Hands out of view this long end a wash. See WASH_GAP_S in app/handwash.py.
    handwash_gap_s: float = 1.5


@lru_cache
def get_settings() -> Settings:
    return Settings()
