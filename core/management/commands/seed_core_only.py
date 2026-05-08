from django.core.management import BaseCommand, CommandError, call_command


class Command(BaseCommand):
    help = "Pipeline seed core uniquement (institution + about + media minimal)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-media",
            action="store_true",
            help="Ne pas executer seed_core_media_minimal.",
        )

    def handle(self, *args, **options):
        skip_media = options.get("skip_media", False)

        pipeline = [
            "seed_core_institution",
            "seed_about",
        ]

        if not skip_media:
            pipeline.append("seed_core_media_minimal")

        self.stdout.write(self.style.NOTICE("\nDemarrage du seed core uniquement..."))

        for command_name in pipeline:
            self.stdout.write(f"-> Execution: {command_name}")
            try:
                call_command(command_name)
            except CommandError as exc:
                raise CommandError(
                    f"Pipeline interrompu sur '{command_name}'. Erreur: {exc}"
                )

        self.stdout.write(self.style.SUCCESS("\nSeed core termine avec succes."))
