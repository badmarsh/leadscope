from datetime import date, timedelta
from pathlib import Path
from typing import List, Optional
import yaml
from pydantic import BaseModel, Field, ValidationError, ValidationInfo, field_validator
from rich.console import Console
from rich.table import Table

console = Console()


class VirusTotalPivot(BaseModel):
    hashes: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)


class Campaign(BaseModel):
    id: str
    name: str
    family: str
    added: date
    stale_after_days: int
    source_url: str
    publicwww_query: Optional[str] = None
    fit: Optional[str] = None
    location: str
    urlscan_pivot: List[str] = Field(default_factory=list)
    virustotal_pivot: VirusTotalPivot = Field(default_factory=VirusTotalPivot)
    notes: Optional[str] = None

    @property
    def is_template(self) -> bool:
        if self.publicwww_query and "{{" in self.publicwww_query and "}}" in self.publicwww_query:
            return True
        for query in self.urlscan_pivot:
            if "{{" in query and "}}" in query:
                return True
        return False

    @property
    def is_stale(self) -> bool:
        expiration_date = self.added + timedelta(days=self.stale_after_days)
        return date.today() > expiration_date

    @property
    def days_old(self) -> int:
        return (date.today() - self.added).days


def load_campaigns(path: str | Path = "campaigns.yaml", raise_on_invalid: bool = False) -> List[Campaign]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Campaign file not found: {file_path}")

    with file_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data or "campaigns" not in data:
        raise ValueError("Invalid campaigns.yaml structure: missing 'campaigns' key.")

    campaigns = []
    for item in data["campaigns"]:
        try:
            c = Campaign(**item)
            campaigns.append(c)
        except ValidationError as err:
            if raise_on_invalid:
                raise
            else:
                cid = item.get("id", "unknown")
                console.print(
                    f"[yellow]Warning: Skipped template/invalid campaign '{cid}': {err.errors()[0]['msg']}[/yellow]"
                )

    return campaigns


def freshness_gate(campaigns: List[Campaign], force_stale: bool = False) -> None:
    table = Table(title="Stage D — Campaign Freshness Summary")
    table.add_column("Campaign ID", style="cyan")
    table.add_column("Family", style="magenta")
    table.add_column("Added Date", style="blue")
    table.add_column("Stale After", style="yellow")
    table.add_column("Age (Days)", style="white")
    table.add_column("Status", style="bold")

    has_stale = False
    for c in campaigns:
        stale = c.is_stale
        if stale:
            has_stale = True
            status_str = "[bold red]STALE[/bold red]"
        else:
            status_str = "[bold green]FRESH[/bold green]"

        table.add_row(
            c.id,
            c.family,
            str(c.added),
            f"{c.stale_after_days} days",
            f"{c.days_old} d",
            status_str,
        )

    console.print(table)

    if has_stale and not force_stale:
        raise ValueError(
            "One or more campaigns are STALE. "
            "Please update campaigns.yaml with fresh IOCs or run with --i-know-this-is-stale"
        )
        
    has_template = False
    for c in campaigns:
        if c.is_template:
            has_template = True
            
    if has_template:
        raise ValueError("One or more campaigns are templates (contain unresolved {{ }} placeholders). Please instantiate them first.")
