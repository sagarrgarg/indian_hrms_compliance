frappe.pages["payroll-control"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Payroll Control Center"),
		single_column: true,
	});

	const state = { company: null, overview: null, preview: null };

	const $body = $(`
		<div class="pcc" style="max-width:1100px;margin:0 auto;">
			<div class="pcc-controls" style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;margin:8px 0 16px;"></div>
			<div class="pcc-kpis" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px;"></div>
			<div style="display:grid;grid-template-columns:1.3fr 1fr;gap:16px;align-items:start;">
				<div class="pcc-run"></div>
				<div class="pcc-readiness"></div>
			</div>
			<div class="pcc-compliance" style="margin-top:16px;"></div>
			<div class="pcc-runs" style="margin-top:16px;"></div>
			<div class="pcc-links" style="margin-top:16px;"></div>
		</div>
	`).appendTo(page.body);

	// CSS (solid colours, no gradients)
	frappe.dom.set_style(`
		.pcc-card{background:#fff;border:1px solid #ececec;border-radius:12px;padding:16px;box-shadow:0 1px 2px rgba(0,0,0,.03);}
		.pcc-card h3{font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.06em;color:#374151;margin:0 0 12px;}
		.pcc-kpi{background:#fff;border:1px solid #ececec;border-radius:12px;padding:14px;}
		.pcc-kpi .v{font-size:26px;font-weight:700;color:#111827;line-height:1;}
		.pcc-kpi .l{font-size:11px;color:#6b7280;margin-top:6px;}
		.pcc-kpi .dot{display:inline-block;height:8px;width:8px;border-radius:50%;margin-right:6px;}
		.pcc-chk{display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid #f3f4f6;}
		.pcc-chk:last-child{border-bottom:0;}
		.pcc-badge{height:20px;width:20px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;color:#fff;font-size:12px;font-weight:700;}
		.pcc-chk .t{font-size:13px;color:#1f2937;font-weight:600;}
		.pcc-chk .d{font-size:11px;color:#6b7280;}
		.pcc-chk a{font-size:11px;color:#4338ca;}
		.pcc-row{display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid #f3f4f6;font-size:13px;}
		.pcc-pill{font-size:10px;font-weight:700;padding:2px 8px;border-radius:9px;}
		.pcc-link{display:inline-flex;align-items:center;gap:6px;background:#eef2ff;color:#4338ca;border-radius:8px;padding:8px 12px;font-size:12px;font-weight:600;margin:4px 6px 4px 0;text-decoration:none;}
	`);

	const $controls = $body.find(".pcc-controls");
	const fg = new frappe.ui.FieldGroup({
		body: $controls[0],
		fields: [
			{ fieldname: "company", fieldtype: "Link", label: __("Company"), options: "Company", reqd: 1 },
			{ fieldtype: "Column Break" },
			{ fieldname: "start_date", fieldtype: "Date", label: __("Period From") },
			{ fieldname: "end_date", fieldtype: "Date", label: __("Period To") },
		],
	});
	fg.make();

	fg.get_field("company").df.onchange = () => {
		state.company = fg.get_value("company");
		loadOverview();
	};

	page.set_primary_action(__("Run Monthly Payroll"), () => runPayroll(), "play");
	page.add_inner_button(__("Preview"), () => previewRun());
	page.add_inner_button(__("Refresh"), () => loadOverview());

	const tone = {
		brand: "#4338ca", green: "#059669", violet: "#7c3aed", amber: "#d97706", grey: "#9ca3af", red: "#dc2626",
	};

	function loadOverview() {
		frappe.dom.freeze(__("Loading payroll overview…"));
		frappe
			.call({ method: "indian_hrms_compliance.api.payroll_desk.get_payroll_overview", args: { company: state.company } })
			.then((r) => {
				frappe.dom.unfreeze();
				if (!r.message) return;
				state.overview = r.message;
				state.company = r.message.company;
				fg.set_value("company", r.message.company);
				if (!fg.get_value("start_date")) fg.set_value("start_date", r.message.suggested_period.start_date);
				if (!fg.get_value("end_date")) fg.set_value("end_date", r.message.suggested_period.end_date);
				render();
			})
			.catch(() => frappe.dom.unfreeze());
	}

	function render() {
		renderKpis();
		renderReadiness();
		renderRun();
		renderCompliance();
		renderRuns();
		renderLinks();
	}

	function renderKpis() {
		const html = (state.overview.kpis || [])
			.map(
				(k) => `<div class="pcc-kpi"><div class="v"><span class="dot" style="background:${tone[k.tone] || tone.grey}"></span>${k.value}</div><div class="l">${frappe.utils.escape_html(k.label)}</div></div>`
			)
			.join("");
		$body.find(".pcc-kpis").html(html);
	}

	function renderReadiness() {
		const rd = state.overview.readiness;
		const er = state.overview.employee_readiness || {};
		const items = (rd.items || [])
			.map((i) => {
				const badge = i.ok
					? `<span class="pcc-badge" style="background:#059669">✓</span>`
					: `<span class="pcc-badge" style="background:#d97706">!</span>`;
				return `<div class="pcc-chk">${badge}<div style="flex:1"><div class="t">${frappe.utils.escape_html(i.label)}</div><div class="d">${frappe.utils.escape_html(i.detail || "")}</div></div>${i.route ? `<a href="${i.route}" target="_blank">${__("Open")}</a>` : ""}</div>`;
			})
			.join("");
		const erBar = er.total
			? `<div style="margin-top:12px;"><div style="font-size:11px;color:#6b7280;">${__("Employee setup")}: ${er.ready}/${er.total} ${__("ready")} (${er.pct}%)</div><div style="height:6px;background:#f3f4f6;border-radius:3px;overflow:hidden;margin-top:4px;"><div style="height:100%;width:${er.pct}%;background:#059669;"></div></div></div>`
			: "";
		$body.find(".pcc-readiness").html(
			`<div class="pcc-card"><h3>${__("Payroll Readiness")}</h3>${items}${erBar}</div>`
		);
	}

	function renderRun() {
		const ready = state.overview.readiness.ready;
		const banner = ready
			? `<div style="font-size:12px;color:#059669;margin-bottom:10px;">✓ ${__("Ready to run payroll")}</div>`
			: `<div style="font-size:12px;color:#d97706;margin-bottom:10px;">⚠ ${__("Resolve the flagged readiness items first")}</div>`;
		let preview = "";
		if (state.preview) {
			const p = state.preview;
			preview = `<div style="margin-top:12px;padding:12px;background:#f9fafb;border-radius:8px;border:1px solid #eef0f2;">
				<div class="pcc-row"><span>${__("Eligible employees")}</span><b>${p.eligible_count}</b></div>
				<div class="pcc-row"><span>${__("Projected base total")}</span><b>${format_currency(p.projected_base_total, "INR")}</b></div>
				<div class="pcc-row" style="border-bottom:0;"><span>${__("Already processed")}</span><b>${p.already_processed}</b></div>
				${p.eligible_count === 0 ? `<div style="font-size:11px;color:#dc2626;margin-top:6px;">${__("No eligible employees — assign salary structures or check already-processed slips.")}</div>` : ""}
			</div>`;
		}
		$body.find(".pcc-run").html(
			`<div class="pcc-card"><h3>${__("Run Monthly Payroll")}</h3>${banner}
			<p style="font-size:12px;color:#6b7280;margin:0 0 8px;">${__("Pick a period above, Preview the headcount, then Run. A draft Payroll Entry with Salary Slips is created for you to review & submit.")}</p>
			${preview}</div>`
		);
	}

	function renderCompliance() {
		const c = state.overview.compliance || {};
		const row = (r, late) =>
			`<div class="pcc-row"><span>${frappe.utils.escape_html(r.return_type || "")} <span style="color:#9ca3af">${frappe.utils.escape_html(r.period_label || "")}</span></span>
			<span><span style="color:#6b7280;font-size:11px;margin-right:8px;">${__("due")} ${frappe.datetime.str_to_user(r.due_date)}</span>
			<span class="pcc-pill" style="background:${late ? "#fee2e2" : "#fef3c7"};color:${late ? "#dc2626" : "#d97706"}">${late ? __("{0}d late", [r.days_late]) : __("upcoming")}</span></span></div>`;
		const overdue = (c.overdue || []).map((r) => row(r, true)).join("");
		const soon = (c.due_soon || []).map((r) => row(r, false)).join("");
		const body =
			overdue || soon
				? overdue + soon
				: `<div style="font-size:12px;color:#059669;">${__("No overdue or upcoming statutory filings 🎉")}</div>`;
		$body.find(".pcc-compliance").html(
			`<div class="pcc-card"><h3>${__("Statutory Deadlines (45 days)")}</h3>${body}
			<div style="margin-top:10px;"><a class="pcc-link" href="/app/compliance-filing" target="_blank">${__("Open Compliance Calendar")}</a></div></div>`
		);
	}

	function renderRuns() {
		const runs = state.overview.recent_runs || [];
		const body = runs.length
			? runs
					.map(
						(r) => `<div class="pcc-row"><a href="/app/payroll-entry/${encodeURIComponent(r.name)}" target="_blank">${r.name}</a>
				<span><span style="color:#6b7280;font-size:11px;margin-right:8px;">${frappe.datetime.str_to_user(r.start_date)} – ${frappe.datetime.str_to_user(r.end_date)}</span>
				<span class="pcc-pill" style="background:#eef2ff;color:#4338ca;">${frappe.utils.escape_html(r.status || "")}</span></span></div>`
					)
					.join("")
			: `<div style="font-size:12px;color:#9ca3af;">${__("No payroll runs yet.")}</div>`;
		$body.find(".pcc-runs").html(`<div class="pcc-card"><h3>${__("Recent Payroll Runs")}</h3>${body}</div>`);
	}

	function renderLinks() {
		const links = [
			["New Employee", "/app/new-employee-setup"],
			["Salary Structures", "/app/salary-structure"],
			["Salary Assignments", "/app/salary-structure-assignment"],
			["Income Tax Slab", "/app/income-tax-slab"],
			["TDS Challan", "/app/tds-challan"],
			["Form 24Q", "/app/tds-return-form-24q"],
			["Form 16", "/app/form-16"],
			["Statutory Mapping", "/app/statutory-component-mapping"],
		];
		$body.find(".pcc-links").html(
			`<div class="pcc-card"><h3>${__("Quick Links")}</h3>${links
				.map(([t, u]) => `<a class="pcc-link" href="${u}" target="_blank">${__(t)}</a>`)
				.join("")}</div>`
		);
	}

	function previewRun() {
		const v = fg.get_values();
		if (!v || !v.start_date || !v.end_date) {
			frappe.msgprint(__("Pick a period first."));
			return;
		}
		frappe.dom.freeze(__("Previewing…"));
		frappe
			.call({
				method: "indian_hrms_compliance.api.payroll_desk.get_run_preview",
				args: { company: state.company, start_date: v.start_date, end_date: v.end_date },
			})
			.then((r) => {
				frappe.dom.unfreeze();
				state.preview = r.message;
				renderRun();
			})
			.catch(() => frappe.dom.unfreeze());
	}

	function runPayroll() {
		const v = fg.get_values();
		if (!v || !v.start_date || !v.end_date) {
			frappe.msgprint(__("Pick a period first."));
			return;
		}
		frappe.confirm(
			__("Create a Payroll Entry and draft Salary Slips for {0} → {1}?", [v.start_date, v.end_date]),
			() => {
				frappe.dom.freeze(__("Creating payroll run…"));
				frappe
					.call({
						method: "indian_hrms_compliance.api.payroll_desk.run_payroll",
						args: { company: state.company, start_date: v.start_date, end_date: v.end_date },
					})
					.then((r) => {
						frappe.dom.unfreeze();
						if (!r.message) return;
						frappe.show_alert({
							message: __("Payroll Entry {0} created for {1} employees", [r.message.payroll_entry, r.message.employees]),
							indicator: "green",
						});
						frappe.set_route("Form", "Payroll Entry", r.message.payroll_entry);
					})
					.catch(() => frappe.dom.unfreeze());
			}
		);
	}

	loadOverview();
};
