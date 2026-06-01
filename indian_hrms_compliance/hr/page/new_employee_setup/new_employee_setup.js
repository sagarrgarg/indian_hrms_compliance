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
			{ fieldname: "aadhaar_last_4", fieldtype: "Data", label: __("Aadhaar (last 4)") },
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
			{ fieldname: "default_shift", fieldtype: "Link", label: __("Default Shift"), options: "Shift Type" },
		],
	});
	fg.make();

	// Prefill from a self-service onboarding application (HR clicked "Convert to
	// Employee"). The application name is carried via route_options and passed
	// back on create so the application gets stamped Converted.
	let onboardingApplication = null;
	const routedApp = frappe.route_options && frappe.route_options.application;
	if (routedApp) {
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
				delete m.onboarding_application;
				Object.keys(m).forEach((k) => {
					if (m[k]) fg.set_value(k, m[k]);
				});
				frappe.show_alert({
					message: __("Prefilled from onboarding application {0}", [onboardingApplication]),
					indicator: "blue",
				});
			});
	}

	// default payroll effective date = DOJ
	fg.get_field("date_of_joining").df.onchange = () => {
		if (fg.get_value("date_of_joining") && !fg.get_value("payroll_effective_date")) {
			fg.set_value("payroll_effective_date", fg.get_value("date_of_joining"));
		}
	};

	page.set_primary_action(__("Create Employee"), () => {
		const values = fg.get_values(); // null + highlights if mandatory missing
		if (!values) return;
		if (onboardingApplication) values.onboarding_application = onboardingApplication;
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
			fg.clear();
			fg.set_value("create_user", 1);
			fg.set_value("send_welcome_email", 1);
			fg.set_value("create_user_permission", 1);
			$result.empty();
			frappe.utils.scroll_to(0);
		});
	}
};
