from django.contrib.auth.views import LoginView as DjangoLoginView

from .forms import LoginForm


class LoginView(DjangoLoginView):
    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        # Without "remember me" the session ends when the browser closes; with it, SESSION_COOKIE_AGE applies.
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)
        return response
