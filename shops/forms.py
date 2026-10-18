import re

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from catalog.models import Product

from .models import Shop

TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,50}$")


class SignupForm(UserCreationForm):
    shop_name = forms.CharField(label="Do'kon nomi", max_length=120)

    class Meta:
        model = User
        fields = ("username",)

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            Shop.objects.create(owner=user, name=self.cleaned_data["shop_name"])
        return user


class ShopForm(forms.ModelForm):
    bot_token = forms.CharField(
        label="Telegram bot tokeni",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}),
        help_text="@BotFather dan olingan token. Bo'sh qoldirsangiz, joriy token o'zgarmaydi.",
    )

    class Meta:
        model = Shop
        fields = ["name", "bot_token", "default_language", "delivery_info", "work_hours", "extra_instructions", "is_active"]
        widgets = {
            "delivery_info": forms.Textarea(attrs={"rows": 3}),
            "extra_instructions": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_bot_token(self):
        token = (self.cleaned_data.get("bot_token") or "").strip()
        if not token:
            return self.instance.bot_token  # o'zgartirilmaydi
        if not TOKEN_RE.match(token):
            raise forms.ValidationError("Token formati noto'g'ri. Namuna: 123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        if Shop.objects.filter(bot_token=token).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Bu token boshqa do'konga ulangan.")
        return token


class CatalogUploadForm(forms.Form):
    file = forms.FileField(label="Excel (.xlsx) yoki CSV fayl")


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "category", "price", "stock", "sku", "description", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}
