"""The collector: every stage, re-exported from wartrack.stages (one module per area) so `from wartrack import collect as C` keeps working."""
from .stages.common import ISO, now_iso, parse_when, log, Scope, alliance_countries  # noqa: F401
from .stages.battles import collect_battles, LEVELS, collect_stats, STATUSES, collect_contracts  # noqa: F401
from .stages.people import collect_people, _refresh_mus, _resolve_players, BOUNTY_TYPES, collect_bounty, collect_wealth, collect_alliances  # noqa: F401
from .stages.money import collect_transfers, collect_trades, collect_donations  # noqa: F401
from .stages.economy import collect_regions, snapshot_wages, collect_companies  # noqa: F401
from .stages.efficiency import ECO_SKILLS, skill_points, collect_efficiency  # noqa: F401
from .stages.maintenance import prune  # noqa: F401
