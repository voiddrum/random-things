import uvicorn

from voider.config import load_config


def main() -> None:
    cfg = load_config()
    uvicorn.run(
        "voider.server:app",
        host=cfg.host,
        port=cfg.port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
