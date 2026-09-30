from frappe.model.document import Document


class AXKChainTrade(Document):
	"""One live lot from registration through inspection, escrow and settlement on Stellar.

	Written by axk_capstone.chain; every on-chain step stores its transaction hash here.
	"""
