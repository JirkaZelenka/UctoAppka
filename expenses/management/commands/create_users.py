from django.core.management.base import BaseCommand
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Vytvoří dva základní uživatelské účty pro aplikaci'

    def handle(self, *args, **options):
        # Vytvoření prvního uživatele
        username1 = 'user1'
        if not User.objects.filter(username=username1).exists():
            user1 = User.objects.create_user(
                username=username1,
                email='user1@example.com',
                password='change_me_123'  # Uživatel by měl změnit heslo po prvním přihlášení
            )
            self.stdout.write(
                self.style.SUCCESS(f'Uživatel "{username1}" byl úspěšně vytvořen. Heslo: change_me_123')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Uživatel "{username1}" již existuje.')
            )

        # Vytvoření druhého uživatele
        username2 = 'user2'
        if not User.objects.filter(username=username2).exists():
            user2 = User.objects.create_user(
                username=username2,
                email='user2@example.com',
                password='change_me_123'  # Uživatel by měl změnit heslo po prvním přihlášení
            )
            self.stdout.write(
                self.style.SUCCESS(f'Uživatel "{username2}" byl úspěšně vytvořen. Heslo: change_me_123')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'Uživatel "{username2}" již existuje.')
            )

        self.stdout.write(
            self.style.SUCCESS('\nOba uzivatele byli vytvoreni. Nezapomente zmenit hesla po prvnim prihlaseni!')
        )

