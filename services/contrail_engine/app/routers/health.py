from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    try:
        import pycontrails  # noqa: F401
        pycontrails_available = True
    except ImportError:
        pycontrails_available = False

    return {
        "status": "healthy",
        "pycontrails_available": pycontrails_available,
        "version": "0.1.0",
    }
