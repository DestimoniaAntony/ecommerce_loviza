"""
Management command: create_superadmin
Creates the CommerceHub Super Admin user.
Usage: python manage.py create_superadmin
"""
from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    help = 'Create the CommerceHub Super Admin user'

    def add_arguments(self, parser):
        parser.add_argument('--phone',    default='9999999999', help='Phone number')
        parser.add_argument('--password', default='Admin@12345',  help='Password')
        parser.add_argument('--email',    default='admin@commercehub.in', help='Email')

    def handle(self, *args, **options):
        phone    = options['phone']
        password = options['password']
        email    = options['email']

        if User.objects.filter(phone=phone).exists():
            self.stdout.write(f'Super admin with phone {phone} already exists.')
            return

        user = User.objects.create_superuser(
            phone=phone,
            password=password,
            email=email,
            first_name='Super',
            last_name='Admin',
        )
        self.stdout.write(self.style.SUCCESS(
            f'Super admin created! Phone: {phone} | Password: {password}'
        ))
