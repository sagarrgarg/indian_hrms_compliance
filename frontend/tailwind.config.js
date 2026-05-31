import frappeUIPreset from "frappe-ui/src/tailwind/preset"
import colors from "tailwindcss/colors"

export default {
	presets: [frappeUIPreset],
	content: [
		"./index.html",
		"./src/**/*.{vue,js,ts,jsx,tsx}",
		"./node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}",
		"../node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}",
	],
	theme: {
		extend: {
			// frappe-ui's preset replaces theme.colors with a limited palette,
			// dropping standard Tailwind colors. Re-add the ones the cockpit /
			// Home UI use so their bg/from/to utilities generate.
			colors: {
				indigo: colors.indigo,
				violet: colors.violet,
				purple: colors.purple,
				emerald: colors.emerald,
				teal: colors.teal,
				sky: colors.sky,
				blue: colors.blue,
				cyan: colors.cyan,
				amber: colors.amber,
				orange: colors.orange,
				lime: colors.lime,
				fuchsia: colors.fuchsia,
				pink: colors.pink,
				rose: colors.rose,
				red: colors.red,
				green: colors.green,
			},
			screens: {
				standalone: {
					raw: "(display-mode: standalone)",
				},
			},
			padding: {
				"safe-top": "env(safe-area-inset-top)",
				"safe-right": "env(safe-area-inset-right)",
				"safe-bottom": "env(safe-area-inset-bottom)",
				"safe-left": "env(safe-area-inset-left)",
			},
		},
	},
	plugins: [],
}
