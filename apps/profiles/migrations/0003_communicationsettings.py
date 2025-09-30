# Generated migration for CommunicationSettings model

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0002_alter_user_groups_alter_user_user_permissions'),  # Replace with actual last migration
    ]

    operations = [
        migrations.CreateModel(
            name='CommunicationSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('telegram_enabled', models.BooleanField(default=False)),
                ('telegram_value', models.CharField(blank=True, max_length=100, null=True)),
                ('whatsapp_enabled', models.BooleanField(default=False)),
                ('whatsapp_value', models.CharField(blank=True, max_length=100, null=True)),
                ('call_enabled', models.BooleanField(default=False)),
                ('call_value', models.CharField(blank=True, help_text='10-digit phone number', max_length=15, null=True)),
                ('map_location_enabled', models.BooleanField(default=False)),
                ('map_location_value', models.URLField(blank=True, help_text='Google Maps link', null=True)),
                ('website_enabled', models.BooleanField(default=False)),
                ('website_value', models.URLField(blank=True, help_text='Website URL', null=True)),
                ('instagram_enabled', models.BooleanField(default=False)),
                ('instagram_value', models.URLField(blank=True, help_text='Instagram profile link', null=True)),
                ('facebook_enabled', models.BooleanField(default=False)),
                ('facebook_value', models.URLField(blank=True, help_text='Facebook profile link', null=True)),
                ('user_profile', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='communication_settings', to='profiles.userprofile')),
            ],
            options={
                'verbose_name': 'Communication Settings',
                'verbose_name_plural': 'Communication Settings',
            },
        ),
    ]