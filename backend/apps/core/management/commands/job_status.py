import json

from django.core.management.base import BaseCommand, CommandError

from apps.core import jobs


class Command(BaseCommand):
    help = (
        "Show the recorded state of every scheduled job: success, failed, running, never (no run recorded) or unknown (started and never "
        "finished). Exit code 1 if any job is not healthy (failed, unknown, never run, or overdue) — use it from monitoring. "
        "State comes only from recorded runs: a job that never ran is NOT reported as fine."
    )

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="machine-readable output")
        parser.add_argument("--job", action="append", help="only this job (repeatable)")

    def handle(self, *args, **options):
        states = jobs.all_job_states()
        if options["job"]:
            unknown = [j for j in options["job"] if j not in jobs.JOBS]
            if unknown:
                raise CommandError(f"unknown job: {', '.join(unknown)}")
            states = [s for s in states if s["name"] in options["job"]]
        bad = [s for s in states if not jobs.is_healthy(s)]
        if options["json"]:
            self.stdout.write(json.dumps([{**{k: v for k, v in s.items() if k != "label"}, **{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in s.items() if k in ("last_started", "last_finished", "last_success")}} for s in states], indent=1))
        else:
            for s in states:
                fmt = lambda d: d.strftime("%Y-%m-%d %H:%M:%S UTC") if d else "-"  # noqa: E731
                self.stdout.write(f"{s['name']:<26} {s['state']:<8} {'OVERDUE ' if s['overdue'] else ''}last_success={fmt(s['last_success'])} processed={s['processed'] if s['processed'] is not None else '-'} errors={s['errors'] if s['errors'] is not None else '-'}{(' error=' + s['error_class']) if s['error_class'] and s['state'] == 'failed' else ''}")
        if bad:
            raise CommandError(f"{len(bad)} job(s) not healthy: {', '.join(s['name'] for s in bad)}")
