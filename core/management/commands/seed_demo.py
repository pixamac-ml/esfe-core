from django.core.management import BaseCommand, CommandError, call_command


class Command(BaseCommand):
    help = "Run a complete demo data seed pipeline for production preview environments."

    def add_arguments(self, parser):
        parser.add_argument(
            "--with-community",
            action="store_true",
            help="Include community topics/answers seed (not idempotent).",
        )

    def handle(self, *args, **options):
        include_community = options.get("with_community", False)

        # Safe default pipeline: mostly idempotent commands.
        pipeline = [
            "seed_core_institution",
            "setup_staff_groups",
            "seed_formations",
            "seed_news",
            "seed_media",
            "seed_results_annexes",
            "seed_blog_live",
            "setup_gamification",
        ]

        if include_community:
            pipeline.append("seed_community")

        self.stdout.write(self.style.WARNING("Starting demo seed pipeline..."))

        for command_name in pipeline:
            self.stdout.write(f"\n-> Running: {command_name}")
            try:
                call_command(command_name)
            except CommandError as exc:
                raise CommandError(
                    f"Seed pipeline stopped at '{command_name}'. Error: {exc}"
                )

        self.stdout.write(self.style.SUCCESS("Demo seed pipeline completed successfully."))

