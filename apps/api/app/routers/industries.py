from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..industries import catalog
from ..models import User

router = APIRouter(prefix="/industries", tags=["industries"])


@router.get("")
def list_industries(user: User = Depends(get_current_user)):
    """The industry catalog with its business types, labelled in both UI languages."""
    return catalog()
