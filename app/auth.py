import os
from fastapi import Request
from starlette.responses import RedirectResponse

def is_admin(request: Request) -> bool:
    return bool(request.session.get("is_admin"))

def require_admin(request: Request):
    if not is_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
    return None

def check_credentials(username: str, password: str) -> bool:
    admin_u = os.getenv("ADMIN_USERNAME", "admin")
    admin_p = os.getenv("ADMIN_PASSWORD", "12345")
    return username == admin_u and password == admin_p