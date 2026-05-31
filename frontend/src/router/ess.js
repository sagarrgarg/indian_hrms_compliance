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
]

export default routes
