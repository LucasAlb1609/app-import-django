# Generated by Django 5.2.1 on 2025-06-04 12:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_import', '0002_remove_importeddata_imported_at_edital_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='importeddata',
            name='coluna1',
        ),
        migrations.RemoveField(
            model_name='importeddata',
            name='coluna2',
        ),
        migrations.RemoveField(
            model_name='importeddata',
            name='coluna3',
        ),
        migrations.AddField(
            model_name='importeddata',
            name='dados_linha',
            field=models.JSONField(default={}),
            preserve_default=False,
        ),
    ]
