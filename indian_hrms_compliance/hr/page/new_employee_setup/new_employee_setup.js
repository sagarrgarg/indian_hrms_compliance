frappe.pages["new-employee-setup"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("New Employee Setup"),
		single_column: true,
	});

	const $body = $('<div class="new-employee-setup p-3" style="max-width: 920px;"></div>').appendTo(page.body);
	const $form = $('<div class="nes-form"></div>').appendTo($body);
	const $result = $('<div class="nes-result mt-4"></div>').appendTo($body);

	const companyQuery = () => ({ filters: { company: fg.get_value("company") } });
	const activeInCompany = () => ({ filters: { company: fg.get_value("company"), status: "Active" } });
	const approverQuery = () => ({
		filters: { company: fg.get_value("company"), status: "Active", user_id: ["is", "set"] },
	});

	const fg = new frappe.ui.FieldGroup({
		body: $form[0],
		fields: [
			{ fieldtype: "Section Break", label: __("Employee Details") },
			{ fieldname: "first_name", fieldtype: "Data", label: __("First Name"), reqd: 1 },
			{ fieldname: "middle_name", fieldtype: "Data", label: __("Middle Name") },
			{ fieldname: "last_name", fieldtype: "Data", label: __("Last Name") },
			{ fieldtype: "Column Break" },
			{ fieldname: "company", fieldtype: "Link", label: __("Company"), options: "Company", reqd: 1 },
			{ fieldname: "department", fieldtype: "Link", label: __("Department"), options: "Department", get_query: companyQuery },
			{ fieldname: "designation", fieldtype: "Link", label: __("Designation"), options: "Designation" },
			{ fieldname: "grade", fieldtype: "Link", label: __("Employee Grade"), options: "Employee Grade" },

			{ fieldtype: "Section Break", label: __("Dates & Type") },
			{ fieldname: "date_of_joining", fieldtype: "Date", label: __("Date of Joining"), reqd: 1 },
			{ fieldname: "date_of_birth", fieldtype: "Date", label: __("Date of Birth"), reqd: 1 },
			{ fieldtype: "Column Break" },
			{ fieldname: "gender", fieldtype: "Link", label: __("Gender"), options: "Gender", reqd: 1 },
			{ fieldname: "employment_type", fieldtype: "Link", label: __("Employment Type"), options: "Employment Type" },

			{ fieldtype: "Section Break", label: __("Login & Access") },
			{ fieldname: "create_user", fieldtype: "Check", label: __("Create User Login"), default: 1 },
			{ fieldname: "user_email", fieldtype: "Data", label: __("User Email"), options: "Email", depends_on: "create_user", mandatory_depends_on: "create_user" },
			{ fieldtype: "Column Break" },
			{ fieldname: "send_welcome_email", fieldtype: "Check", label: __("Send Welcome Email"), default: 1, depends_on: "create_user" },
			{ fieldname: "create_user_permission", fieldtype: "Check", label: __("Restrict User to this Company"), default: 1, depends_on: "create_user" },

			{ fieldtype: "Section Break", label: __("Statutory IDs") },
			{ fieldname: "pan_number", fieldtype: "Data", label: __("PAN"), reqd: 1 },
			{ fieldname: "aadhaar_number", fieldtype: "Data", label: __("Aadhaar Number"), length: 12, description: __("12 digits; auto-derives last 4 for legacy reports.") },
			{ fieldname: "aadhaar_last_4", fieldtype: "Data", label: __("Aadhaar (last 4)"), read_only: 1 },
			{ fieldname: "uan_number", fieldtype: "Data", label: __("UAN") },
			{ fieldtype: "Column Break" },
			{ fieldname: "provident_fund_account", fieldtype: "Data", label: __("PF Account") },
			{ fieldname: "esic_ip_number", fieldtype: "Data", label: __("ESIC IP Number") },
			{ fieldname: "bank_name", fieldtype: "Data", label: __("Bank Name") },
			{ fieldname: "bank_ac_no", fieldtype: "Data", label: __("Bank A/C No") },
			{ fieldname: "ifsc_code", fieldtype: "Data", label: __("IFSC Code") },

			{ fieldtype: "Section Break", label: __("Reporting & Approvers") },
			{ fieldname: "reports_to", fieldtype: "Link", label: __("Reports To"), options: "Employee", get_query: activeInCompany },
			{ fieldname: "leave_approver", fieldtype: "Link", label: __("Leave Approver"), options: "Employee", get_query: approverQuery },
			{ fieldtype: "Column Break" },
			{ fieldname: "expense_approver", fieldtype: "Link", label: __("Expense Approver"), options: "Employee", get_query: approverQuery },
			{ fieldname: "shift_request_approver", fieldtype: "Link", label: __("Shift Request Approver"), options: "Employee", get_query: approverQuery },

			{ fieldtype: "Section Break", label: __("Payroll & Shift") },
			{ fieldname: "salary_structure", fieldtype: "Link", label: __("Salary Structure"), options: "Salary Structure", get_query: () => ({ filters: { company: fg.get_value("company"), docstatus: 1, is_active: "Yes" } }) },
			{ fieldname: "base", fieldtype: "Currency", label: __("Base Amount"), depends_on: "salary_structure" },
			{ fieldname: "income_tax_slab", fieldtype: "Link", label: __("Income Tax Slab"), options: "Income Tax Slab", depends_on: "salary_structure" },
			{ fieldtype: "Column Break" },
			{ fieldname: "payroll_effective_date", fieldtype: "Date", label: __("Payroll Effective From"), depends_on: "salary_structure" },
			{ fieldname: "default_shift", fieldtype: "Link", label: __("Default Shift"), options: "Shift Type", reqd: 1 },

			{ fieldtype: "Section Break", label: __("Confirmation & Probation") },
			{ fieldname: "place_on_probation", fieldtype: "Check", label: __("Place on Probation"), default: 0, description: __("Keeps the employee Active for payroll/attendance/leave, while flagging them on probation.") },
			{ fieldname: "probation_months", fieldtype: "Int", label: __("Probation Period (Months)"), depends_on: "place_on_probation", mandatory_depends_on: "place_on_probation", description: __("Confirmation is scheduled this many months after the date of joining.") },
			{ fieldtype: "Column Break" },
			{ fieldname: "final_confirmation_date", fieldtype: "Date", label: __("Confirmation Date"), depends_on: "eval:!doc.place_on_probation", description: __("Defaults to the application submission date. Set it to mark the employee Confirmed.") },

			{ fieldtype: "Section Break", label: __("Leave") },
			{ fieldname: "leave_policy", fieldtype: "Link", label: __("Leave Policy"), options: "Leave Policy", reqd: 1, description: __("Assigned (and allocated) on creation. Prefilled from the company default.") },
			{ fieldtype: "Column Break" },
			{ fieldname: "leave_period", fieldtype: "Link", label: __("Leave Period"), options: "Leave Period", get_query: () => ({ filters: { company: fg.get_value("company") } }) },

			{ fieldtype: "Section Break", label: __("Company Policies to Acknowledge"), description: __("Pre-selected from the company's active policies — untick any this joiner shouldn't have to acknowledge.") },
			{ fieldname: "policies_to_ack", fieldtype: "MultiCheck", label: __("Policies"), columns: 2, select_all: 1, options: [] },
		],
	});
	fg.make();

	// State carried from a self-service onboarding application (HR clicked
	// "Convert to Employee"): passed back on create so the application gets
	// stamped Converted. The actual prefill runs in refresh() (on_page_show).
	let onboardingApplication = null;
	let jobApplicant = null;

	// default payroll effective date = DOJ
	fg.get_field("date_of_joining").df.onchange = () => {
		if (fg.get_value("date_of_joining") && !fg.get_value("payroll_effective_date")) {
			fg.set_value("payroll_effective_date", fg.get_value("date_of_joining"));
		}
	};

	// Live derive last-4 from the full Aadhaar — keeps the legacy column in sync.
	fg.get_field("aadhaar_number").df.onchange = () => {
		const raw = (fg.get_value("aadhaar_number") || "").toString().replace(/\D/g, "");
		if (raw !== fg.get_value("aadhaar_number")) fg.set_value("aadhaar_number", raw);
		fg.set_value("aadhaar_last_4", raw.slice(-4));
	};

	// Company drives the leave policy/period defaults, the suggested probation
	// length, and which company policies are offered for acknowledgement.
	fg.get_field("company").df.onchange = loadCompanyDefaults;

	// on_page_show calls this on every visit (the Desk page wrapper is cached
	// and on_page_load does NOT re-run on soft navigation).
	wrapper.nes_refresh = refresh;

	page.set_primary_action(__("Create Employee"), () => {
		const values = fg.get_values(); // null + highlights if mandatory missing
		if (!values) return;
		if (onboardingApplication) values.onboarding_application = onboardingApplication;
		if (jobApplicant) values.job_applicant = jobApplicant;
		values.policies_to_ack = fg.get_value("policies_to_ack") || [];
		frappe.confirm(__("Create the Employee, User login and linked records now?"), () => {
			frappe.dom.freeze(__("Setting up the new employee…"));
			frappe
				.call({
					method: "indian_hrms_compliance.hr.employee_setup.setup_new_employee",
					args: { data: values },
				})
				.then((r) => {
					frappe.dom.unfreeze();
					if (!r.message) return;
					render_result(r.message);
				})
				.catch(() => frappe.dom.unfreeze());
		});
	});

	// Reset the form to a pristine state, then prefill from a routed onboarding
	// application if one was passed (HR clicked "Convert to Employee"). Runs on
	// every page show so navigating back never leaves the previously-created
	// employee's data on screen, and a fresh conversion always prefills.
	function refresh() {
		fg.clear();
		fg.set_value("create_user", 1);
		fg.set_value("send_welcome_email", 1);
		fg.set_value("create_user_permission", 1);
		fg.set_value("place_on_probation", 0);
		onboardingApplication = null;
		jobApplicant = null;
		setPolicyOptions([]);
		$result.empty();

		const routedApp = frappe.route_options && frappe.route_options.application;
		if (!routedApp) return;
		frappe.route_options = {};
		frappe
			.call({
				method: "indian_hrms_compliance.hr.doctype.employee_onboarding_application.employee_onboarding_application.get_application_for_setup",
				args: { name: routedApp },
			})
			.then((r) => {
				const m = r.message;
				if (!m) return;
				onboardingApplication = m.onboarding_application;
				jobApplicant = m.job_applicant;
				delete m.onboarding_application;
				delete m.job_applicant;
				// Setting `company` here fires its onchange → loadCompanyDefaults(),
				// which prefills the leave policy/period and the policy checklist.
				Object.keys(m).forEach((k) => {
					if (m[k]) fg.set_value(k, m[k]);
				});
				frappe.show_alert({
					message: __("Prefilled from onboarding application {0}", [onboardingApplication]),
					indicator: "blue",
				});
			});
	}

	// Pull the company's leave/probation/policy defaults and prime the form.
	function loadCompanyDefaults() {
		const company = fg.get_value("company");
		if (!company) {
			setPolicyOptions([]);
			return;
		}
		frappe
			.call({
				method: "indian_hrms_compliance.hr.employee_setup.get_setup_defaults",
				args: { company },
			})
			.then((r) => {
				const m = r.message || {};
				// Leave policy/period are Company-scoped — reset them to this
				// company's defaults (clearing any stale prior-company pick).
				fg.set_value("leave_policy", m.leave_policy || "");
				fg.set_value("leave_period", m.leave_period || "");
				if (m.probation_months && !fg.get_value("probation_months")) {
					fg.set_value("probation_months", m.probation_months);
				}
				setPolicyOptions(m.policies || []);
			});
	}

	// Rebuild the policy checklist for the current company, every box pre-ticked.
	function setPolicyOptions(policies) {
		const field = fg.get_field("policies_to_ack");
		field.df.get_data = () =>
			(policies || []).map((p) => ({
				label: p.version ? `${p.policy_name} (v${p.version})` : p.policy_name,
				value: p.name,
				checked: 1,
			}));
		field.refresh();
	}

	function render_result(m) {
		const items = (m.log || []).map((l) => `<li>${frappe.utils.escape_html(l)}</li>`).join("");
		$result.html(`
			<div class="alert alert-success">
				<div style="font-weight:600;margin-bottom:6px;">${__("Employee Created")}: ${frappe.utils.escape_html(m.employee)}</div>
				<ul style="margin:0 0 8px 18px;">${items}</ul>
				<a class="btn btn-xs btn-default" href="/app/employee/${encodeURIComponent(m.employee)}">${__("Open Employee")}</a>
				${m.user ? `<a class="btn btn-xs btn-default" href="/app/user/${encodeURIComponent(m.user)}">${__("Open User")}</a>` : ""}
				<button class="btn btn-xs btn-primary nes-another">${__("Create Another")}</button>
			</div>
		`);
		$result.find(".nes-another").on("click", () => {
			// Pristine reset. route_options was already consumed, so no re-prefill —
			// a fresh manual employee must not inherit the converted one's links.
			refresh();
			frappe.utils.scroll_to(0);
		});
	}
};

frappe.pages["new-employee-setup"].on_page_show = function (wrapper) {
	// The Desk page wrapper is built once and reused across soft navigations,
	// so on_page_load does NOT re-run. Re-prime the form on every show so we
	// never display the previously-created employee's data — or miss a fresh
	// "Convert to Employee" prefill — until a hard refresh.
	if (wrapper && wrapper.nes_refresh) wrapper.nes_refresh();
};
