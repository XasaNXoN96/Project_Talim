from .services import unread_count


def unread(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.has_perm("chat.use_chat"):
        return {}
    return {"unread_chat": unread_count(user)}
