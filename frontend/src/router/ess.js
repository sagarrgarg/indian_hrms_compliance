const routes = [
	{
		name: "PoliciesDashboard",
		path: "/policies",
		component: () => import("@/views/policy/Dashboard.vue"),
	},
	{
		name: "PolicyAcknowledgeView",
		path: "/policies/:id",
		props: true,
		component: () => import("@/views/policy/AcknowledgeView.vue"),
	},
	{
		name: "TasksDashboard",
		path: "/tasks",
		component: () => import("@/views/task/Dashboard.vue"),
	},
	{
		name: "TaskDetailView",
		path: "/tasks/:id",
		props: true,
		component: () => import("@/views/task/TaskDetailView.vue"),
	},
	{
		name: "ExitDashboard",
		path: "/exit",
		component: () => import("@/views/exit/Dashboard.vue"),
	},
	{
		name: "ResignationForm",
		path: "/exit/resign",
		component: () => import("@/views/exit/ResignationForm.vue"),
	},
	{
		name: "GrievancesDashboard",
		path: "/grievances",
		component: () => import("@/views/grievance/Dashboard.vue"),
	},
	{
		name: "GrievanceForm",
		path: "/grievances/new",
		component: () => import("@/views/grievance/GrievanceForm.vue"),
	},
	{
		name: "POSHDashboard",
		path: "/posh",
		component: () => import("@/views/posh/Dashboard.vue"),
	},
	{
		name: "POSHForm",
		path: "/posh/new",
		component: () => import("@/views/posh/POSHForm.vue"),
	},
	{
		name: "POSHDetailView",
		path: "/posh/:id",
		props: true,
		component: () => import("@/views/posh/POSHDetailView.vue"),
	},
	{
		name: "PrivacyDashboard",
		path: "/privacy",
		component: () => import("@/views/privacy/Dashboard.vue"),
	},
	{
		name: "ConsentNoticeView",
		path: "/privacy/consent/:purposeCode",
		props: true,
		component: () => import("@/views/privacy/ConsentNoticeView.vue"),
	},
	{
		name: "ErasureRequestForm",
		path: "/privacy/erasure",
		component: () => import("@/views/privacy/ErasureRequestForm.vue"),
	},
	{
		name: "ApprovalsInbox",
		path: "/approvals",
		component: () => import("@/views/approvals/Inbox.vue"),
	},
	{
		name: "Cockpit",
		path: "/cockpit",
		component: () => import("@/views/Cockpit.vue"),
		beforeEnter: async (to, from, next) => {
			const { canViewCockpit } = await import("@/data/cockpit")
			try {
				await (canViewCockpit.promise || canViewCockpit.reload())
			} catch (e) {
				// fall through — backend get_hr_cockpit still enforces access
			}
			next(canViewCockpit.data === false ? { name: "Home" } : true)
		},
	},
	{
		name: "OrgChart3D",
		path: "/org-chart-3d",
		component: () => import("@/views/OrgChart3D.vue"),
		beforeEnter: async (to, from, next) => {
			const { canViewCockpit } = await import("@/data/cockpit")
			try {
				await (canViewCockpit.promise || canViewCockpit.reload())
			} catch (e) {
				/* backend get_org_graph still enforces access */
			}
			next(canViewCockpit.data === false ? { name: "Home" } : true)
		},
	},
]

export default routes
