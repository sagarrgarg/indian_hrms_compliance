import click
import frappe

from indian_hrms_compliance import compat
from indian_hrms_compliance.setup import after_install as setup

APP = "indian_hrms_compliance"

# This app's own setup patches: custom fields, workflows, seeded defaults, Indian States and PT
# slabs. They start at this entry in patches.txt and run to the end of the file, plus the
# HR Settings seed that sits earlier. Patches before this entry are upstream data migrations.
FIRST_SETUP_PATCH = f"{APP}.patches.v15_0.update_approver_custom_fields"
EARLY_SETUP_PATCHES = [f"{APP}.patches.v15_0.nativize_hr_settings_seed"]

# Patches that only repair or move rows that existed before a change. A new site has no such
# rows, and some of them touch fields that later work removed, so they are not run on install.
DATA_ONLY_PREFIXES = ("backfill_", "migrate_", "fix_", "convert_", "cleanup_", "remove_", "promote_", "link_onboarding_document_files", "posh_text_accused_split", "additional_salary_approval_backfill", "employee_advance_approval_backfill")


def after_install():
	try:
		print("Setting up Frappe HR...")
		setup()
		run_setup_patches()
		compat.hide_half_day_holidays()
		compat.prune_missing_workspace_links()

		click.secho("Thank you for installing Frappe HR!", fg="green")

	except Exception as e:
		BUG_REPORT_URL = "https://github.com/frappe/indian_hrms_compliance/issues/new"
		click.secho(
			"Installation for Frappe HR app failed due to an error."
			" Please try re-installing the app or"
			f" report the issue on {BUG_REPORT_URL} if not resolved.",
			fg="bright_red",
		)
		raise e


def run_setup_patches():
	"""Run this app's setup patches on a fresh install.

	Installing an app marks all of its patches as done without running them, so everything
	they create would exist only on sites that were migrated, never on new ones. Each patch
	is idempotent: it is the same code `bench migrate` ran on the existing sites.
	"""
	from frappe.modules.patch_handler import PatchType, get_patches_from_app, run_single

	patches = get_patches_from_app(APP, PatchType.post_model_sync)
	names = [patch.split()[0] for patch in patches]
	setup_patches = [p for p in patches if p.split()[0] in EARLY_SETUP_PATCHES]
	setup_patches += patches[names.index(FIRST_SETUP_PATCH) :]
	setup_patches = [p for p in setup_patches if not p.split()[0].rsplit(".", 1)[-1].startswith(DATA_ONLY_PREFIXES)]

	print("Running setup patches...")
	failed = []
	developer_mode = frappe.conf.developer_mode  # run_single switches it off for the process
	for patch in setup_patches:
		try:
			run_single(patch, force=True)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			failed.append(patch.split()[0])
			frappe.log_error(f"Setup patch failed on install: {patch}")
	frappe.conf.developer_mode = developer_mode

	if failed:
		click.secho("These setup patches failed (see Error Log): " + ", ".join(failed), fg="yellow")
