"""Language selection.

Django's own mechanism does the work: LocaleMiddleware + the django_language cookie, set by the stock set_language view
(POST only, CSRF-protected, `next` validated against open redirects). On top of that:
  * a signed-in user's choice is also stored in User.locale, so it follows them to another browser;
  * a signed-in user WITHOUT a language cookie (new browser) gets their stored language.
Anonymous pages use the cookie, then the browser's Accept-Language, then the default (uz).
"""
from django.conf import settings
from django.utils import translation
from django.views.decorators.http import require_POST
from django.views.i18n import set_language as django_set_language


class UserLanguageMiddleware:
    """Placed after AuthenticationMiddleware (and after LocaleMiddleware)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and settings.LANGUAGE_COOKIE_NAME not in request.COOKIES:
            lang = getattr(user, "locale", "")
            if lang in dict(settings.LANGUAGES):
                translation.activate(lang)
                request.LANGUAGE_CODE = lang
        return self.get_response(request)


@require_POST
def set_language(request):
    lang = request.POST.get("language", "")
    if lang not in dict(settings.LANGUAGES):
        # Django would accept any language it ships a catalog for (de, fr...). Only OUR languages may be stored.
        request.POST = request.POST.copy()
        request.POST["language"] = ""
        lang = ""
    response = django_set_language(request)
    user = request.user
    if user.is_authenticated and lang in dict(settings.LANGUAGES) and getattr(user, "locale", None) != lang:
        user.locale = lang
        user.save(update_fields=["locale"])
    return response


def user_language(user) -> str:
    """The language for anything sent TO a user (e-mails): their stored choice, else the site default."""
    lang = getattr(user, "locale", "") or ""
    return lang if lang in dict(settings.LANGUAGES) else settings.LANGUAGE_CODE
