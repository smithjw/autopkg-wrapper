import json
import logging
import os
import plistlib
import re
import zipfile
from pathlib import Path


def find_report_dirs(base_path: str) -> list[str]:
    dirs: list[str] = []
    if not os.path.exists(base_path):
        return dirs
    for root, subdirs, _files in os.walk(base_path):
        for d in subdirs:
            if d.startswith("autopkg_report-"):
                dirs.append(os.path.join(root, d))
    if not dirs:
        try:
            has_files = any(
                os.path.isfile(os.path.join(base_path, f))
                for f in os.listdir(base_path)
            )
        except FileNotFoundError:
            has_files = False
        if has_files:
            dirs.append(base_path)
    return sorted(dirs)


def parse_json_file(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _infer_recipe_name_from_filename(path: str) -> str:
    base = os.path.basename(path)
    if base.endswith(".plist"):
        base = base[:-6]
    m = re.search(r"-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})$", base)
    if m:
        return base[: m.start()]
    return base


def _resolve_recipe_name(name: str, recipe_link_map: dict[str, str] | None) -> str:
    if not recipe_link_map:
        return name
    if name in recipe_link_map:
        return name
    candidates = [
        recipe_name
        for recipe_name in recipe_link_map
        if recipe_name.startswith(f"{name}.")
    ]
    if len(candidates) == 1:
        return candidates[0]
    return name


def _build_recipe_link_map(
    repo_path: str | None, repo_url: str | None, repo_branch: str | None
) -> dict[str, str]:
    if not repo_path or not repo_url or not repo_branch:
        return {}
    repo_root = Path(repo_path)
    if not repo_root.exists():
        return {}

    recipe_link_map: dict[str, str] = {}
    for path in repo_root.rglob("*.recipe*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root).as_posix()
        recipe_base = path.name
        recipe_name = recipe_base.split(".recipe", 1)[0]
        if recipe_name not in recipe_link_map:
            recipe_link_map[recipe_name] = f"{repo_url}/blob/{repo_branch}/{rel}"
    return recipe_link_map


def parse_text_file(path: str) -> dict[str, list]:
    uploads: list[dict] = []
    policies: list[dict] = []
    errors: list[str] = []

    re_error = re.compile(r"ERROR[:\s-]+(.+)", re.IGNORECASE)
    re_upload = re.compile(
        r"(Uploaded|Upload|Uploading)[^\n]*?(?P<name>[A-Za-z0-9 ._+\-]+?)(?=(?:\s+\bversion\b)|$)(?:[^\n]*?\bversion\b[^\d]*(?P<version>\d+(?:\.\d+)+))?",
        re.IGNORECASE,
    )
    re_policy = re.compile(r"Policy (created|updated):\s*(?P<name>.+)", re.IGNORECASE)

    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                m_err = re_error.search(line)
                if m_err:
                    errors.append(m_err.group(1).strip())
                    continue

                m_up = re_upload.search(line)
                if m_up:
                    uploads.append(
                        {
                            "name": (m_up.group("name") or "").strip(),
                            "version": (m_up.group("version") or "-") or "-",
                        }
                    )
                    continue

                m_pol = re_policy.search(line)
                if m_pol:
                    action = "updated" if "updated" in line.lower() else "created"
                    policies.append(
                        {
                            "name": m_pol.group("name").strip(),
                            "action": action,
                        }
                    )
    except Exception:
        pass

    return {"uploads": uploads, "policies": policies, "errors": errors}


def parse_plist_file(
    path: str, *, recipe_link_map: dict[str, str] | None = None
) -> dict[str, list]:
    uploads: list[dict] = []
    policies: list[dict] = []
    errors: list[str] = []
    upload_rows: list[dict] = []
    policy_rows: list[dict] = []
    error_rows: list[dict] = []

    try:
        with open(path, "rb") as f:
            plist = plistlib.load(f)
    except Exception:
        return {
            "uploads": uploads,
            "policies": policies,
            "errors": errors,
            "upload_rows": upload_rows,
            "policy_rows": policy_rows,
            "error_rows": error_rows,
        }

    failures = plist.get("failures", []) or []

    sr = plist.get("summary_results", {}) or {}

    recipe_name = _infer_recipe_name_from_filename(path)
    if recipe_link_map:
        recipe_name = _resolve_recipe_name(recipe_name, recipe_link_map)
    recipe_identifier: str | None = None
    recipe_link = (recipe_link_map or {}).get(recipe_name)

    handled_keys: set[str] = set()

    jpu = sr.get("jamfpackageuploader_summary_result")
    if isinstance(jpu, dict):
        handled_keys.add("jamfpackageuploader_summary_result")
        rows = jpu.get("data_rows") or []
        for row in rows:
            name = (row.get("name") or row.get("pkg_display_name") or "-").strip()
            version = (row.get("version") or "-").strip()
            uploads.append({"name": name, "version": version})
            pkg_name = (
                row.get("pkg_name") or row.get("pkg_display_name") or "-"
            ).strip()
            pkg_path = (row.get("pkg_path") or "").strip()
            if pkg_path:
                parts = pkg_path.split("/cache/")
                if len(parts) > 1:
                    after = parts[1]
                    rid = after.split("/")[0]
                    recipe_identifier = rid or recipe_identifier
            upload_rows.append(
                {
                    "recipe_name": recipe_name,
                    "recipe_identifier": recipe_identifier or "-",
                    "recipe_url": recipe_link,
                    "package": pkg_name,
                    "version": version or "-",
                }
            )

    jpol = sr.get("jamfpolicyuploader_summary_result")
    if isinstance(jpol, dict):
        handled_keys.add("jamfpolicyuploader_summary_result")
        rows = jpol.get("data_rows") or []
        for row in rows:
            name = (
                row.get("policy")
                or row.get("policy_name")
                or row.get("name")
                or row.get("title")
            )
            if not name:
                continue
            policies.append({"name": str(name).strip(), "action": "-"})
            policy_rows.append(
                {
                    "recipe_name": recipe_name,
                    "recipe_identifier": recipe_identifier or "-",
                    "recipe_url": recipe_link,
                    "policy": str(name).strip(),
                }
            )

    for key, block in sr.items():
        if key in handled_keys:
            continue
        if not isinstance(block, dict):
            continue
        hdr = [h.lower() for h in (block.get("header") or [])]
        rows = block.get("data_rows") or []
        summary_text = (block.get("summary_text") or "").lower()
        looks_like_policy = (
            "policy" in key.lower()
            or "policy" in summary_text
            or any("policy" in h for h in hdr)
        )
        if looks_like_policy and rows:
            for row in rows:
                name = row.get("policy_name") or row.get("name") or row.get("title")
                action = row.get("action") or row.get("status") or row.get("result")
                if name:
                    policies.append(
                        {
                            "name": str(name).strip(),
                            "action": (str(action).strip() if action else "-"),
                        }
                    )
                    policy_rows.append(
                        {
                            "recipe_name": recipe_name,
                            "recipe_identifier": recipe_identifier or "-",
                            "recipe_url": recipe_link,
                            "policy": str(name).strip(),
                        }
                    )

    for fail in failures:
        if isinstance(fail, dict):
            msg = fail.get("message") or json.dumps(fail)
            rec = fail.get("recipe") or recipe_name
        else:
            msg = str(fail)
            rec = recipe_name
        errors.append(msg)
        error_rows.append(
            {
                "recipe_name": rec,
                "error_type": _classify_error_simple(msg),
            }
        )

    return {
        "uploads": uploads,
        "policies": policies,
        "errors": errors,
        "upload_rows": upload_rows,
        "policy_rows": policy_rows,
        "error_rows": error_rows,
    }


def aggregate_reports(
    base_path: str,
    *,
    recipe_link_map: dict[str, str] | None = None,
) -> dict:
    summary = {
        "uploads": [],
        "policies": [],
        "errors": [],
        "recipes": 0,
        "upload_rows": [],
        "policy_rows": [],
        "error_rows": [],
    }
    report_dirs = find_report_dirs(base_path)

    for repdir in report_dirs:
        for root, _subdirs, files in os.walk(repdir):
            for fn in files:
                p = os.path.join(root, fn)
                ext = os.path.splitext(fn)[1].lower()

                if ext == ".plist":
                    data = parse_plist_file(p, recipe_link_map=recipe_link_map)
                    summary["uploads"] += data.get("uploads", [])
                    summary["policies"] += data.get("policies", [])
                    summary["errors"] += data.get("errors", [])
                    summary["upload_rows"] += data.get("upload_rows", [])
                    summary["policy_rows"] += data.get("policy_rows", [])
                    summary["error_rows"] += data.get("error_rows", [])
                    summary["recipes"] += 1
                elif ext == ".json":
                    data = parse_json_file(p)
                    if not data:
                        continue
                    if isinstance(data, dict):
                        uploads = data.get("uploads")
                        policies = data.get("policies")
                        errors = data.get("errors")
                        recipes = data.get("recipes")
                        if isinstance(uploads, list):
                            summary["uploads"] += uploads
                        if isinstance(policies, list):
                            summary["policies"] += policies
                        if isinstance(errors, list):
                            summary["errors"] += errors
                        if isinstance(errors, list):
                            for e in errors:
                                if isinstance(e, dict):
                                    rn = e.get("recipe") or "-"
                                    msg = e.get("message") or json.dumps(e)
                                    summary["error_rows"].append(
                                        {
                                            "recipe_name": rn,
                                            "error_type": _classify_error_simple(
                                                str(msg)
                                            ),
                                        }
                                    )
                        if isinstance(recipes, int):
                            summary["recipes"] += recipes
                else:
                    data = parse_text_file(p)
                    summary["uploads"] += data.get("uploads", [])
                    summary["policies"] += data.get("policies", [])
                    summary["errors"] += data.get("errors", [])

    return summary


# ---------- Rendering ----------


def _aggregate_for_display(
    summary: dict,
) -> tuple[dict[str, set], dict[str, set], dict[str, int]]:
    uploads = summary.get("uploads", [])
    policies = summary.get("policies", [])
    errors = summary.get("errors", [])

    def plausible_app_name(n: str) -> bool:
        if not n or n == "-":
            return False
        if n.lower() in {"apps", "packages", "pkg", "file", "37"}:
            return False
        return re.search(r"[A-Za-z]", n) is not None

    uploads_by_app: dict[str, set] = {}
    for u in uploads:
        if isinstance(u, dict):
            name = (u.get("name") or "-").strip()
            ver = (u.get("version") or "-").strip()
        else:
            name = str(u).strip()
            ver = "-"
        if not plausible_app_name(name):
            name = "-"
        uploads_by_app.setdefault(name, set()).add(ver)

    policies_by_name: dict[str, set] = {}
    for p in policies:
        if isinstance(p, dict):
            name = (p.get("name") or "-").strip()
            action = (p.get("action") or "-").strip()
        else:
            name = str(p).strip()
            action = "-"
        policies_by_name.setdefault(name, set()).add(action)

    error_categories: dict[str, int] = {
        "trust": 0,
        "signature": 0,
        "download": 0,
        "network": 0,
        "auth": 0,
        "jamf": 0,
        "other": 0,
    }

    def classify_error(msg: str) -> str:
        lm = msg.lower()
        if "trust" in lm:
            return "trust"
        if "signature" in lm or "codesign" in lm:
            return "signature"
        if "download" in lm or "fetch" in lm:
            return "download"
        if (
            "proxy" in lm
            or "timeout" in lm
            or "network" in lm
            or "url" in lm
            or "dns" in lm
        ):
            return "network"
        if (
            "auth" in lm
            or "token" in lm
            or "permission" in lm
            or "401" in lm
            or "403" in lm
        ):
            return "auth"
        if "jamf" in lm or "policy" in lm:
            return "jamf"
        return "other"

    for e in errors:
        emsg = e if isinstance(e, str) else json.dumps(e)
        cat = classify_error(emsg)
        error_categories[cat] = error_categories.get(cat, 0) + 1

    return uploads_by_app, policies_by_name, error_categories


def render_job_summary(summary: dict, environment: str, run_date: str) -> str:
    lines: list[str] = []
    title_bits: list[str] = []
    if environment:
        title_bits.append(environment)
    if run_date:
        title_bits.append(run_date)
    if title_bits:
        lines.append(f"# Autopkg Report Summary ({' '.join(title_bits)})")
    else:
        lines.append("# Autopkg Report Summary")
    lines.append("")

    total_uploads_raw = len(summary.get("uploads", []))
    uploads_by_app, policies_by_name, error_categories = _aggregate_for_display(summary)
    total_uploads_apps = len(uploads_by_app)
    total_policies = len(policies_by_name)
    total_errors = len(summary.get("errors", []))
    recipes = summary.get("recipes") or "N/A"

    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Recipes processed | {recipes} |")
    lines.append(
        f"| Apps uploaded | {total_uploads_apps} (items: {total_uploads_raw}) |"
    )
    lines.append(f"| Policies changed | {total_policies} |")
    lines.append(f"| Errors | {total_errors} |")
    lines.append("")

    if summary.get("upload_rows"):
        lines.append("## Uploaded Recipes")
        lines.append("")
        lines.append("| Recipe Name | Identifier | Package | Version |")
        lines.append("| --- | --- | --- | --- |")
        for row in sorted(
            summary["upload_rows"], key=lambda r: str(r.get("recipe_name", "")).lower()
        ):
            pkg = row.get("package", "-")
            pkg_url = row.get("package_url")
            pkg_cell = f"[{pkg}]({pkg_url})" if pkg_url else pkg
            recipe_name = row.get("recipe_name", "-")
            recipe_url = row.get("recipe_url")
            recipe_cell = (
                f"[{recipe_name}]({recipe_url})" if recipe_url else recipe_name
            )
            lines.append(
                f"| {recipe_cell} | {row.get('recipe_identifier', '-')} | {pkg_cell} | {row.get('version', '-')} |"
            )
        lines.append("")
    else:
        lines.append("No uploads in this run.")
        lines.append("")

    if summary.get("policy_rows"):
        lines.append("## Policy Recipes")
        lines.append("")
        lines.append("| Recipe Name | Identifier | Policy |")
        lines.append("| --- | --- | --- |")
        for row in sorted(
            summary["policy_rows"], key=lambda r: str(r.get("recipe_name", "")).lower()
        ):
            recipe_name = row.get("recipe_name", "-")
            recipe_url = row.get("recipe_url")
            recipe_cell = (
                f"[{recipe_name}]({recipe_url})" if recipe_url else recipe_name
            )
            policy = row.get("policy", "-")
            policy_url = row.get("policy_url")
            policy_cell = f"[{policy}]({policy_url})" if policy_url else policy
            lines.append(
                f"| {recipe_cell} | {row.get('recipe_identifier', '-')} | {policy_cell} |"
            )
        lines.append("")

    if total_errors:
        lines.append("## Errors Summary")
        lines.append("")
        lines.append("| Category | Count |")
        lines.append("| --- | --- |")
        for cat in [
            "trust",
            "signature",
            "download",
            "network",
            "auth",
            "jamf",
            "other",
        ]:
            lines.append(f"| {cat} | {error_categories.get(cat, 0)} |")
        lines.append("")

    return "\n".join(lines)


def render_issue_body(summary: dict, environment: str, run_date: str) -> str:
    lines: list[str] = []
    total_errors = len(summary.get("errors", []))
    _uploads_by_app, _policies_by_name, _error_categories = _aggregate_for_display(
        summary
    )

    prefix = "Autopkg run"
    suffix_bits: list[str] = []
    if run_date:
        suffix_bits.append(f"on {run_date}")
    if environment:
        suffix_bits.append(f"({environment})")
    suffix = (" ".join(suffix_bits)).strip()
    if suffix:
        lines.append(f"{prefix} {suffix} reported {total_errors} error(s).")
    else:
        lines.append(f"{prefix} reported {total_errors} error(s).")
    lines.append("")
    lines.append("### Errors")
    lines.append("| Recipe | Error Type |")
    lines.append("| --- | --- |")
    for row in summary.get("error_rows", []):
        lines.append(
            f"| {row.get('recipe_name', '-')} | {row.get('error_type', 'other')} |"
        )

    lines.append("")

    return "\n".join(lines)


# ---------- Utility ----------


def _redact_sensitive(s: str) -> str:
    s = re.sub(r"ghs_[A-Za-z0-9]+", "ghs_***", s)
    s = re.sub(
        r"(Authorization:\s*token)\s+[A-Za-z0-9_\-]+",
        r"\1 ***",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"(Bearer)\s+[A-Za-z0-9._\-]+", r"\1 ***", s, flags=re.IGNORECASE)
    return s


def _classify_error_simple(msg: str) -> str:
    lm = msg.lower()
    if "trust" in lm:
        return "trust"
    if "signature" in lm or "codesign" in lm:
        return "signature"
    if (
        "401" in lm
        or "403" in lm
        or "auth" in lm
        or "token" in lm
        or "permission" in lm
    ):
        return "auth"
    if "download" in lm or "fetch" in lm or "curl" in lm:
        return "download"
    if (
        "proxy" in lm
        or "timeout" in lm
        or "network" in lm
        or "url" in lm
        or "dns" in lm
    ):
        return "network"
    if "jamf" in lm or "policy" in lm:
        return "jamf"
    return "other"


# ---------- Jamf Helpers ----------


def _normalize_host(url: str) -> str:
    h = (url or "").strip()
    if h.startswith("https://"):
        h = h[len("https://") :]
    if h.startswith("http://"):
        h = h[len("http://") :]
    return h.rstrip("/")


def build_pkg_map(jss_url: str, client_id: str, client_secret: str) -> dict[str, str]:
    host = _normalize_host(jss_url)
    _ = host  # silence linters about unused var; kept for readability
    pkg_map: dict[str, str] = {}
    try:
        from jamf_pro_sdk import (  # type: ignore
            ApiClientCredentialsProvider,
            JamfProClient,
        )

        client = JamfProClient(
            _normalize_host(jss_url),
            ApiClientCredentialsProvider(client_id, client_secret),
        )
        packages = client.pro_api.get_packages_v1()
        for p in packages:
            try:
                name = str(p.packageName).strip()
                pid = str(p.id).strip()
            except Exception as e:  # noqa: F841
                # ignore objects that do not match expected shape
                continue
            if not name or not pid:
                continue
            url = f"{jss_url}/view/settings/computer-management/packages/{pid}"
            if name not in pkg_map:
                pkg_map[name] = url
    except Exception as e:  # noqa: F841
        return {}
    return pkg_map


def build_policy_map(
    jss_url: str, client_id: str, client_secret: str
) -> dict[str, str]:
    host = _normalize_host(jss_url)
    _ = host  # silence linters about unused var; kept for readability
    policy_map: dict[str, str] = {}
    try:
        from jamf_pro_sdk import (  # type: ignore
            ApiClientCredentialsProvider,
            JamfProClient,
        )

        client = JamfProClient(
            _normalize_host(jss_url),
            ApiClientCredentialsProvider(client_id, client_secret),
        )
        policies = client.pro_api.get_policies()
        for p in policies:
            try:
                name = str(p.name).strip()
                pid = str(p.id).strip()
            except Exception:
                continue
            if not name or not pid:
                continue
            url = f"{jss_url}/policies.html?id={pid}"
            if name not in policy_map:
                policy_map[name] = url
    except Exception:
        return {}
    return policy_map


def enrich_upload_rows(upload_rows: list[dict], pkg_map: dict[str, str]) -> int:
    linked = 0
    norm_map = {k.lower(): v for k, v in pkg_map.items()}
    for row in upload_rows:
        pkg_name = str(row.get("package") or "").strip()
        url = pkg_map.get(pkg_name) or norm_map.get(pkg_name.lower())
        if url:
            row["package_url"] = url
            linked += 1
    return linked


def enrich_policy_rows(policy_rows: list[dict], policy_map: dict[str, str]) -> int:
    linked = 0
    norm_map = {k.lower(): v for k, v in policy_map.items()}
    for row in policy_rows:
        policy_name = str(row.get("policy") or "").strip()
        url = policy_map.get(policy_name) or norm_map.get(policy_name.lower())
        if url:
            row["policy_url"] = url
            linked += 1
    return linked


def enrich_upload_rows_with_jamf(
    summary: dict, jss_url: str, client_id: str, client_secret: str
) -> tuple[int, list[str]]:
    pkg_map = build_pkg_map(jss_url, client_id, client_secret)
    linked = enrich_upload_rows(summary.get("upload_rows", []), pkg_map)
    return linked, sorted(set(pkg_map.keys()))


def enrich_policy_rows_with_jamf(
    summary: dict, jss_url: str, client_id: str, client_secret: str
) -> tuple[int, list[str]]:
    policy_map = build_policy_map(jss_url, client_id, client_secret)
    linked = enrich_policy_rows(summary.get("policy_rows", []), policy_map)
    return linked, sorted(set(policy_map.keys()))


def process_reports(
    *,
    zip_file: str | None,
    extract_dir: str,
    reports_dir: str | None,
    environment: str = "",
    run_date: str = "",
    out_dir: str,
    debug: bool,
    strict: bool,
    repo_url: str | None = None,
    repo_branch: str | None = None,
    repo_path: str | None = None,
) -> int:
    os.makedirs(out_dir, exist_ok=True)

    if zip_file:
        zpath = zip_file
        if not os.path.exists(zpath):
            raise FileNotFoundError(f"zip file not found: {zpath}")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(zpath, "r") as zf:
            zf.extractall(extract_dir)
        process_dir = extract_dir
    else:
        process_dir = reports_dir or extract_dir

    recipe_link_map = _build_recipe_link_map(repo_path, repo_url, repo_branch)
    summary = aggregate_reports(process_dir, recipe_link_map=recipe_link_map)

    jss_url = os.environ.get("AUTOPKG_JSS_URL")
    jss_client_id = os.environ.get("AUTOPKG_CLIENT_ID")
    jss_client_secret = os.environ.get("AUTOPKG_CLIENT_SECRET")
    jamf_attempted = False
    jamf_linked = 0
    jamf_keys: list[str] = []
    jamf_policy_linked = 0
    jamf_policy_keys: list[str] = []
    jamf_total = len(summary.get("upload_rows", []))
    jamf_policy_total = len(summary.get("policy_rows", []))
    if (
        jss_url
        and jss_client_id
        and jss_client_secret
        and (jamf_total or jamf_policy_total)
    ):
        jamf_attempted = True
        try:
            if jamf_total:
                jamf_linked, jamf_keys = enrich_upload_rows_with_jamf(
                    summary, jss_url, jss_client_id, jss_client_secret
                )
            if jamf_policy_total:
                jamf_policy_linked, jamf_policy_keys = enrich_policy_rows_with_jamf(
                    summary, jss_url, jss_client_id, jss_client_secret
                )
        except Exception:
            jamf_linked = 0
            jamf_policy_linked = 0

    job_md = render_job_summary(summary, environment, run_date)
    issue_md = None
    if summary.get("errors"):
        issue_md = render_issue_body(summary, environment, run_date)

    with open(os.path.join(out_dir, "job_summary.md"), "w", encoding="utf-8") as f:
        f.write(job_md)

    if issue_md:
        with open(os.path.join(out_dir, "errors_issue.md"), "w", encoding="utf-8") as f:
            f.write(issue_md)

    jamf_log_path = ""
    if debug:
        jamf_log_path = os.path.join(out_dir, "jamf_lookup_debug.json")
        try:
            upload_pkg_names = [
                str(r.get("package") or "").strip()
                for r in summary.get("upload_rows", [])
            ]
            policy_names = [
                str(r.get("policy") or "").strip()
                for r in summary.get("policy_rows", [])
            ]
            matched = [
                r for r in summary.get("upload_rows", []) if r.get("package_url")
            ]
            unmatched = [
                r for r in summary.get("upload_rows", []) if not r.get("package_url")
            ]
            policy_matched = [
                r for r in summary.get("policy_rows", []) if r.get("policy_url")
            ]
            policy_unmatched = [
                r for r in summary.get("policy_rows", []) if not r.get("policy_url")
            ]
            diag = {
                "jss_url": jss_url or "",
                "jamf_keys_count": len(jamf_keys),
                "jamf_keys_sample": jamf_keys[:20],
                "jamf_policy_keys_count": len(jamf_policy_keys),
                "jamf_policy_keys_sample": jamf_policy_keys[:20],
                "uploads_count": len(upload_pkg_names),
                "matched_count": len(matched),
                "unmatched_count": len(unmatched),
                "unmatched_names": [r.get("package") for r in unmatched][:20],
                "policies_count": len(policy_names),
                "policy_matched_count": len(policy_matched),
                "policy_unmatched_count": len(policy_unmatched),
                "policy_unmatched_names": [r.get("policy") for r in policy_unmatched][
                    :20
                ],
            }
            with open(jamf_log_path, "w", encoding="utf-8") as jf:
                json.dump(diag, jf, indent=2)
        except Exception:
            jamf_log_path = ""

    status = [
        f"Processed reports in '{process_dir}'. Recipes: {summary.get('recipes', 'N/A')}",
        f"Summary: '{os.path.join(out_dir, 'job_summary.md')}'",
        f"Errors file: {'errors_issue.md' if issue_md else 'none'}",
    ]
    if jamf_attempted:
        status.append(
            f"Jamf links added: packages {jamf_linked}/{jamf_total}, policies {jamf_policy_linked}/{jamf_policy_total}"
        )
        if jamf_log_path:
            status.append(f"Jamf lookup log: '{jamf_log_path}'")
    else:
        status.append("Jamf links: skipped (missing env or no uploads/policies)")
    logging.info(". ".join(status))

    if strict and summary.get("errors"):
        return 1
    return 0
