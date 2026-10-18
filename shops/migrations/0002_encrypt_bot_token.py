from django.db import migrations, models

from shops.crypto import encrypt, token_hash


def encrypt_existing_tokens(apps, schema_editor):
    Shop = apps.get_model("shops", "Shop")
    seen = set()
    for shop in Shop.objects.exclude(bot_token=""):
        digest = token_hash(shop.bot_token)
        if digest in seen:  # takroriy token: keyingisini bo'shatamiz (egasi qayta kiritadi)
            continue
        seen.add(digest)
        shop.token_encrypted = encrypt(shop.bot_token)
        shop.token_hash = digest
        shop.save(update_fields=["token_encrypted", "token_hash"])


class Migration(migrations.Migration):
    dependencies = [("shops", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="shop",
            name="token_encrypted",
            field=models.TextField(blank=True, default="", editable=False),
        ),
        migrations.AddField(
            model_name="shop",
            name="token_hash",
            field=models.CharField(blank=True, default="", editable=False, max_length=64),
        ),
        migrations.RunPython(encrypt_existing_tokens, migrations.RunPython.noop),
        migrations.RemoveField(model_name="shop", name="bot_token"),
        migrations.AddConstraint(
            model_name="shop",
            constraint=models.UniqueConstraint(
                condition=models.Q(("token_hash", ""), _negated=True),
                fields=("token_hash",),
                name="uniq_shop_token_hash",
            ),
        ),
    ]
