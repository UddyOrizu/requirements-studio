"""M9 file exports: render the chosen formats from the IR, zip them, store them, keep the history.

Every file comes from a renderer (M7, M10, M11, exporters); nothing is hand-edited. An export is tied to the IR
version and hash it came from and is never changed; re-exporting identical content returns the earlier export.
"""
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from exporters import ado_csv, backlog_csv, backlog_xlsx, improvements_md, jira_csv, workbook_rows
from flow_renderer import render_drawio, render_mermaid
from ir_core import Issue, PatchRejected, canonical_json, ir_hash
from services.common.db import utcnow
from services.common.events import EventEnvelope
from services.common.outbox import enqueue_event
from services.common.settings import Settings
from services.ideas.db import Idea
from services.ideas.service import IdeasService
from services.identity_audit.audit import write_audit
from services.ir_store.service import NotFound, iso
from story_renderer import render_gherkin, render_markdown
from story_renderer.markdown import draft_banner

from .db import ExportRow
from .store import ExportStore

ZIP_TIME = (2026, 1, 1, 0, 0, 0)  # fixed, so the same files give the same zip
CONTENT_TYPES = {".csv": "text/csv", ".md": "text/markdown", ".feature": "text/plain", ".mmd": "text/vnd.mermaid",
                 ".drawio": "application/vnd.jgraph.mxfile",
                 ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
FORMATS = [  # (id, label, import into)
    ("lucidchart", "Lucidchart (.drawio)", "Lucidchart, draw.io"),
    ("mermaid", "Mermaid (.mmd)", "Lucid diagram-as-code, wikis"),
    ("markdown", "Markdown (stories, improvements)", "Confluence, SharePoint, wikis"),
    ("gherkin", "Gherkin (.feature)", "Cucumber, SpecFlow, Behave"),
    ("jira", "Jira CSV", "Jira Cloud CSV importer"),
    ("ado", "Azure DevOps CSV", "Azure Boards CSV import"),
    ("excel", "Excel workbook", "Excel, Google Sheets"),
    ("csv", "Backlog CSV", "Any tool"),
]
FORMAT_IDS = [f[0] for f in FORMATS]


@dataclass
class Rendered:
    process_id: str
    ir: dict
    variant: str
    files: dict[str, bytes]
    hash_basis: dict[str, str]  # file → sha256 used for de-duplication (the xlsx is hashed by its rows)
    draft: bool
    not_ready: int


def feature_name(process_id: str) -> str:
    """proc_client_kyc_to_be → client_kyc.feature"""
    return process_id.removeprefix("proc_").removesuffix("_to_be").removesuffix("_as_is") + ".feature"


class ExportService:
    def __init__(self, session: AsyncSession, settings: Settings, store: ExportStore, *, clock=utcnow,
                 correlation_id: str | None = None):
        self.s, self.settings, self.store, self.clock = session, settings, store, clock
        self.ideas = IdeasService(session, clock=clock, correlation_id=correlation_id)
        self.correlation_id = self.ideas.patches.correlation_id

    async def formats(self, idea_id: str) -> dict:
        idea = await self.ideas.idea(idea_id)
        defaults = {"lucidchart", "markdown", self.settings.default_tracker}
        files = await self._files_by_format(idea)
        return {"formats": [{"id": fid, "label": label, "import_into": into, "default": fid in defaults,
                             "files": files[fid]} for fid, label, into in FORMATS],
                "variants": [v for v, pid in (("to_be", idea.to_be_process_id), ("as_is", idea.as_is_process_id))
                             if pid],
                "ado_process": self.settings.ado_process}

    async def _files_by_format(self, idea: Idea) -> dict[str, list[str]]:
        flows = [v for v, pid in (("as_is", idea.as_is_process_id), ("to_be", idea.to_be_process_id)) if pid]
        process = idea.to_be_process_id or idea.as_is_process_id
        has_suggestions = bool(idea.as_is_process_id and idea.to_be_process_id)
        return {"lucidchart": [f"flow/{v}_process_flow.drawio" for v in flows],
                "mermaid": [f"flow/{v}_process_flow.mmd" for v in flows],
                "markdown": ["stories.md", *(["improvements.md"] if has_suggestions else [])],
                "gherkin": [f"features/{feature_name(process)}"], "jira": ["jira_import.csv"],
                "ado": ["azure_devops_import.csv"], "excel": ["stories_backlog.xlsx"], "csv": ["stories_backlog.csv"]}

    # ------------------------------------------------------------------ render
    @staticmethod
    def _check_formats(formats: list[str]) -> list[str]:
        unknown = sorted(set(formats) - set(FORMAT_IDS))
        if unknown or not formats:
            raise PatchRejected([Issue("envelope", "/formats", f"choose formats from {FORMAT_IDS}"
                                       + (f"; unknown: {unknown}" if unknown else ""))])
        return sorted(set(formats), key=FORMAT_IDS.index)

    async def render(self, idea_id: str, formats: list[str], variant: str | None = None) -> Rendered:
        formats = self._check_formats(formats)
        idea = await self.ideas.idea(idea_id)
        ctx = await self.ideas.context(idea, variant)
        ir, stories, rows = ctx.ir, ctx.stories, list(ctx.rows.values())
        p = ir["process"]
        not_ready = sum(r["status"] not in ("ready", "waived") for r in rows)
        draft = not_ready > 0
        suggestions = [r.as_suggestion() for r in await self.ideas._suggestions(idea.id)]
        summary = p.get("description") or idea.summary
        files: dict[str, bytes] = {}
        basis: dict[str, str] = {}

        def add(name: str, text: str | bytes, hash_of: str | None = None):
            data = text.encode() if isinstance(text, str) else text
            files[name] = data
            basis[name] = hash_of or hashlib.sha256(data).hexdigest()

        if {"lucidchart", "mermaid"} & set(formats):
            for v, pid in (("as_is", idea.as_is_process_id), ("to_be", idea.to_be_process_id)):
                if pid:
                    flow_ir = await self.ideas.patches.get_ir(pid)
                    if "lucidchart" in formats:
                        add(f"flow/{v}_process_flow.drawio", render_drawio(flow_ir))
                    if "mermaid" in formats:
                        add(f"flow/{v}_process_flow.mmd", render_mermaid(flow_ir))
        if "markdown" in formats:
            origin = f"the {p['variant'].replace('_', '-')} process (v{p['version']}) (polish off)"
            add("stories.md", render_markdown(ir, rows, as_is=ctx.as_is, origin=origin, draft=draft))
            if suggestions and ctx.as_is:
                add("improvements.md", improvements_md(ctx.as_is, ir, suggestions,
                                                       draft_banner=draft_banner(not_ready) if draft else None))
        if "gherkin" in formats:
            add(f"features/{feature_name(p['id'])}", render_gherkin(ir))
        if "jira" in formats:
            add("jira_import.csv", jira_csv(ir, stories, idea.title, summary, draft=draft))
        if "ado" in formats:
            add("azure_devops_import.csv", ado_csv(ir, stories, idea.title, summary,
                                                   process=self.settings.ado_process, draft=draft))
        if "excel" in formats:
            sheets = workbook_rows(ir, stories, ctx.as_is, suggestions)
            add("stories_backlog.xlsx", backlog_xlsx(ir, stories, ctx.as_is, suggestions),
                hashlib.sha256(canonical_json(sheets)).hexdigest())
        if "csv" in formats:
            add("stories_backlog.csv", backlog_csv(ir, stories))
        return Rendered(p["id"], ir, p["variant"], files, basis, draft, not_ready)

    async def preview(self, idea_id: str, fmt: str, variant: str | None = None) -> dict:
        """What the export screen shows: CSV first rows, Markdown in full, sheet rows for Excel."""
        rendered = await self.render(idea_id, [fmt], variant)
        out = []
        for name, data in rendered.files.items():
            if name.endswith(".xlsx"):
                ctx = await self.ideas.context(await self.ideas.idea(idea_id), variant)
                text = "\n".join(" | ".join(str(c) for c in row[:6]) for row in
                                 workbook_rows(ctx.ir, ctx.stories)["Stories"][:8])
            elif name.endswith(".csv"):
                text = "\n".join(data.decode().splitlines()[:12])
            else:
                text = data.decode()
            out.append({"file": name, "kind": name.rsplit(".", 1)[-1], "text": text[:20000]})
        return {"files": out, "draft": rendered.draft, "not_ready": rendered.not_ready}

    # ------------------------------------------------------------------ export, history, download
    async def create(self, idea_id: str, formats: list[str], *, user_id: str, variant: str | None = None) -> dict:
        formats = self._check_formats(formats)
        rendered = await self.render(idea_id, formats, variant)
        listing = [{"name": n, "sha256": rendered.hash_basis[n], "size": len(d),
                    "content_type": CONTENT_TYPES.get("." + n.rsplit(".", 1)[-1], "application/octet-stream")}
                   for n, d in sorted(rendered.files.items())]
        package_hash = hashlib.sha256(json.dumps(listing, sort_keys=True).encode()).hexdigest()
        existing = (await self.s.execute(select(ExportRow).where(
            ExportRow.process_id == rendered.process_id, ExportRow.mode == "files",
            ExportRow.package_hash == package_hash))).scalar_one_or_none()
        if existing:
            return self._out(existing)

        row = ExportRow(process_id=rendered.process_id, ir_version=rendered.ir["process"]["version"],
                        ir_hash=ir_hash({k: v for k, v in rendered.ir.items() if k != "stories"}),
                        package_hash=package_hash, mode="files", status="ready", idea_id=idea_id,
                        variant=rendered.variant, formats=formats, files=listing,
                        draft=rendered.draft, created_by=user_id)
        self.s.add(row)
        await self.s.flush()
        row.uri = await self.store.put(_key(row), _zip(rendered.files))
        previous = (await self.s.execute(select(ExportRow).where(
            ExportRow.process_id == row.process_id, ExportRow.mode == "files", ExportRow.id != row.id,
            ExportRow.superseded_by.is_(None)))).scalars()
        for old in previous:
            old.superseded_by = row.id
        await write_audit(self.s, actor_kind="user", actor_id=user_id, action="export.created", target=str(row.id),
                          process_id=row.process_id, after={"formats": row.formats, "ir_version": row.ir_version,
                                                            "draft": row.draft})
        await enqueue_event(self.s, EventEnvelope(type="export.created", process_id=row.process_id,
                                                  ir_version=row.ir_version, correlation_id=self.correlation_id,
                                                  payload={"export_id": str(row.id), "package_uri": row.uri,
                                                           "ir_hash": row.ir_hash}))
        await self.s.flush()
        return self._out(row)

    async def history(self, idea_id: str) -> list[dict]:
        await self.ideas.idea(idea_id)
        q = select(ExportRow).where(ExportRow.idea_id == idea_id).order_by(ExportRow.created_at.desc(),
                                                                          ExportRow.id.desc())
        return [self._out(r) for r in (await self.s.execute(q)).scalars()]

    async def get(self, export_id: str) -> ExportRow:
        row = await self.s.get(ExportRow, UUID(export_id))
        if row is None:
            raise NotFound(f"export {export_id} not found")
        return row

    async def download(self, export_id: str, file: str | None = None) -> tuple[bytes, str, str]:
        """(content, filename, content type): one file from the export, or the whole zip."""
        row = await self.get(export_id)
        data = await self.store.get(_key(row))
        if file is None:
            return data, f"{row.idea_id or row.process_id}_v{row.ir_version}_export.zip", "application/zip"
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if file not in z.namelist():
                raise NotFound(f"{file} is not in export {export_id}")
            content = z.read(file)
        return content, file.rsplit("/", 1)[-1], CONTENT_TYPES.get("." + file.rsplit(".", 1)[-1],
                                                                   "application/octet-stream")

    @staticmethod
    def _out(r: ExportRow) -> dict:
        return {"export_id": str(r.id), "process_id": r.process_id, "ir_version": r.ir_version, "ir_hash": r.ir_hash,
                "package_hash": r.package_hash, "formats": r.formats, "files": r.files, "variant": r.variant,
                "draft": r.draft, "created_by": r.created_by, "created_at": iso(r.created_at), "status": r.status,
                "superseded_by": str(r.superseded_by) if r.superseded_by else None}


def _key(row: ExportRow) -> str:
    """{process_id}/{export_id}.zip in the exports container (or under RS_EXPORT_DIR)."""
    return f"{row.process_id}/{row.id}.zip"


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(files):
            z.writestr(zipfile.ZipInfo(name, date_time=ZIP_TIME), files[name])
    return buf.getvalue()
