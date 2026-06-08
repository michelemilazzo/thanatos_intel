import frappe

no_cache = 0


def get_context(context):
	context.no_cache = 0
	context.services = [
		("Antifrode", "Prevenzione e accertamento di frodi: analisi di pattern, blacklist, wallet crypto, scam. Supporto a denunce e recuperi."),
		("Due Diligence", "Verifica di controparti, soci e fornitori prima di un accordo: identità, reputazione, esposizione legale e finanziaria."),
		("OSINT", "Intelligence da fonti aperte su persone, aziende, domini, email, dati esposti. Connettori HIBP, sanzioni, RDAP e altri."),
		("Due Diligence Diplomatica", "Valutazione di eleggibilità e dossier per percorsi diplomatici/consolari, con screening sanzioni, KYC/KYB e identificazione a distanza."),
		("Cyber Intelligence", "Monitoraggio minacce, esposizione dati, rischio cyber e crypto-scam intelligence per aziende e studi."),
		("Corporate Intelligence", "Analisi societaria, beneficial owner, cariche, esposizione debitoria e documentale su entità nazionali ed estere."),
		("Sequestri & Confische", "Supporto investigativo e documentale per procedure di sequestro e confisca, con tracciabilità delle prove."),
		("Newsroom", "Analisi e notizie quotidiane su frodi, cyber e investigazioni, contestualizzate per i professionisti."),
	]
