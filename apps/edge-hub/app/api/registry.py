from fastapi import APIRouter
from app.commands.command_registry import command_registry

router = APIRouter()

@router.get("/registry")
def list_registry():
    """Expose the loaded command table for UI/debug."""
    return command_registry.list_all()
