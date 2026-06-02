import { createResource } from "frappe-ui"

const base = "indian_hrms_compliance.api.tax_declaration."

// No persisted cache: the period/declaration must reflect current server state
// (a stale localStorage cache was showing a null payroll period after the
// national-period change).
export const myTaxDeclaration = createResource({
	url: base + "get_my_tax_declaration",
})

export const saveTaxDeclaration = createResource({ url: base + "save_my_tax_declaration" })
export const compareRegimes = createResource({ url: base + "compare_tax_regimes" })
export const submitTaxProof = createResource({ url: base + "submit_tax_proof" })
