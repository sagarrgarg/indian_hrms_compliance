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
]

export default routes
