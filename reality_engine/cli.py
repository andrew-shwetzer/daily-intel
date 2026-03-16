"""CLI interface for Reality Engine."""

import logging
import sys
from pathlib import Path

import click

from reality_engine.config import Config, DEFAULT_CONFIG_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("reality_engine")


def _find_config(instance: str | None = None) -> Path:
    """Find config file for an instance."""
    if instance:
        config_path = DEFAULT_CONFIG_DIR / "instances" / instance / "config.yaml"
    else:
        # Look for single instance
        instances_dir = DEFAULT_CONFIG_DIR / "instances"
        if not instances_dir.exists():
            click.echo("No instances found. Run the /reality-engine skill in Claude Code to set up.")
            sys.exit(1)

        instances = [d for d in instances_dir.iterdir() if d.is_dir()]
        if len(instances) == 0:
            click.echo("No instances found. Run the /reality-engine skill in Claude Code to set up.")
            sys.exit(1)
        elif len(instances) == 1:
            config_path = instances[0] / "config.yaml"
        else:
            click.echo("Multiple instances found. Specify one:")
            for inst in instances:
                click.echo(f"  - {inst.name}")
            sys.exit(1)

    if not config_path.exists():
        click.echo(f"Config not found: {config_path}")
        sys.exit(1)

    return config_path


@click.group()
@click.option("--instance", "-i", default=None, help="Instance name (slug)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
@click.pass_context
def cli(ctx, instance, verbose):
    """Reality Engine - AI-powered industry intelligence monitoring."""
    if verbose:
        logging.getLogger("reality_engine").setLevel(logging.DEBUG)
    ctx.ensure_object(dict)
    ctx.obj["instance"] = instance


@cli.command()
@click.pass_context
def collect(ctx):
    """Collect signals from all configured sources."""
    config = Config.load(_find_config(ctx.obj["instance"]))
    errors = config.validate()
    if errors:
        for e in errors:
            click.echo(f"Config error: {e}")
        sys.exit(1)

    from reality_engine.collector import collect_all

    signals = collect_all(config, use_db=True)
    click.echo(f"Collected {len(signals)} signals above threshold")


@cli.command()
@click.pass_context
def brief(ctx):
    """Generate and deliver the daily intelligence brief."""
    config = Config.load(_find_config(ctx.obj["instance"]))
    errors = config.validate()
    if errors:
        for e in errors:
            click.echo(f"Config error: {e}")
        sys.exit(1)

    from reality_engine.briefer import generate_brief
    from reality_engine.delivery import deliver

    brief_data = generate_brief(config, use_db=True)

    if brief_data["metadata"]["signal_count"] == 0:
        click.echo("No signals to brief on. Run 'collect' first.")
        return

    click.echo(f"Brief generated: {brief_data['metadata']['editorial_headline']}")
    click.echo(f"  Signals: {brief_data['metadata']['signal_count']}")
    click.echo(f"  P1 (act today): {brief_data['metadata']['p1_count']}")
    click.echo(f"  P2 (this week): {brief_data['metadata']['p2_count']}")

    results = deliver(config, brief_data)
    for channel, success in results.items():
        status = "delivered" if success else "FAILED"
        click.echo(f"  {channel}: {status}")


@cli.command()
@click.pass_context
def run(ctx):
    """Collect signals and generate brief (full cycle)."""
    ctx.invoke(collect)
    ctx.invoke(brief)


@cli.command()
@click.pass_context
def health(ctx):
    """Check system health."""
    config = Config.load(_find_config(ctx.obj["instance"]))

    click.echo(f"Instance: {config.niche}")
    click.echo(f"Sources: {len(config.sources)}")
    click.echo(f"Competitors: {len(config.competitors)}")
    click.echo(f"Delivery: {config.delivery.method}")

    errors = config.validate()
    if errors:
        click.echo(f"\nConfig issues:")
        for e in errors:
            click.echo(f"  - {e}")
    else:
        click.echo(f"\nConfig: OK")

    # Check DB if configured
    if config.database.supabase_url:
        try:
            from reality_engine.db import get_signal_count_today, get_source_stats

            count = get_signal_count_today(config)
            stats = get_source_stats(config)
            click.echo(f"\nToday's signals: {count}")
            if stats:
                click.echo("By source type:")
                for source_type, n in stats.items():
                    click.echo(f"  {source_type}: {n}")

            if count == 0:
                click.echo("\nHealth: YELLOW - No signals collected today")
            else:
                click.echo(f"\nHealth: GREEN")
        except Exception as e:
            click.echo(f"\nHealth: RED - Database error: {e}")
    else:
        click.echo("\nDatabase: Not configured")


@cli.command()
@click.pass_context
def preview(ctx):
    """Preview: collect and generate a brief without storing anything."""
    config = Config.load(_find_config(ctx.obj["instance"]))

    if not config.sources:
        click.echo("No sources configured.")
        sys.exit(1)

    click.echo(f"Collecting signals for: {config.niche}")
    click.echo(f"Sources: {len(config.sources)}")
    click.echo("")

    from reality_engine.collector import collect_all
    from reality_engine.briefer import generate_brief

    signals = collect_all(config, use_db=False)

    if not signals:
        click.echo("No signals found above threshold. Try adjusting min_relevance or adding more sources.")
        return

    click.echo(f"\nScored {len(signals)} signals. Generating brief...\n")

    brief_data = generate_brief(config, signals=signals, use_db=False)
    click.echo(brief_data["markdown"])


@cli.command()
def list_instances():
    """List all configured instances."""
    instances_dir = DEFAULT_CONFIG_DIR / "instances"
    if not instances_dir.exists():
        click.echo("No instances configured.")
        return

    for inst_dir in sorted(instances_dir.iterdir()):
        if inst_dir.is_dir() and (inst_dir / "config.yaml").exists():
            config = Config.load(inst_dir / "config.yaml")
            click.echo(f"  {inst_dir.name}: {config.niche} ({len(config.sources)} sources)")
