
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from catalog.models import Product

from .crypto import token_hash
from .models import Shop

from .botconfig import TOKEN_RE


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
    # Model maydoni emas: token shifrlanib saqlanadi (view da qo'lda o'rnatiladi)
    bot_token = forms.CharField(
        label="Telegram bot tokeni",
        required=False,
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}),
        help_text="@BotFather dan olingan token. Bo'sh qoldirsangiz, joriy token o'zgarmaydi.",
    )
    remove_token = forms.BooleanField(
        label="Joriy tokenni o'chirish (botni uzish)", required=False
    )

    class Meta:
        model = Shop
        fields = ["name", "default_language", "delivery_info", "work_hours", "extra_instructions", "is_active"]
        widgets = {
            "delivery_info": forms.Textarea(attrs={"rows": 3}),
            "extra_instructions": forms.Textarea(attrs={"rows": 3}),
        }

    field_order = ["name", "bot_token", "remove_token", "default_language", "delivery_info", "work_hours", "extra_instructions", "is_active"]

    def clean_bot_token(self):
        token = (self.cleaned_data.get("bot_token") or "").strip()
        if not token:
            return ""
        if not TOKEN_RE.match(token):
            raise forms.ValidationError("Token formati noto'g'ri. Namuna: 123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        if Shop.objects.filter(token_hash=token_hash(token)).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Bu token boshqa do'konga ulangan.")
        return token

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("bot_token") and cleaned.get("remove_token"):
            raise forms.ValidationError("Yangi token kiritib, bir vaqtda uni o'chirib bo'lmaydi.")
        return cleaned


class CatalogUploadForm(forms.Form):
    file = forms.FileField(label="Excel (.xlsx) yoki CSV fayl")


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "category", "price", "stock", "sku", "description", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def clean_price(self):
        from django.conf import settings

        price = self.cleaned_data["price"]
        if price > settings.MAX_PRICE:
            raise forms.ValidationError("Narx juda katta.")
        return price

    def clean_stock(self):
        from django.conf import settings

        stock = self.cleaned_data["stock"]
        if stock > settings.MAX_STOCK:
            raise forms.ValidationError("Qoldiq juda katta.")
        return stock
