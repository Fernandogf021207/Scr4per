"""Configuración para el scraper de Facebook"""

FACEBOOK_CONFIG = {
	"base_url": "https://www.facebook.com/",
	# Asegúrate de haber guardado tu sesión en este archivo
	# Puedes iniciar el navegador, loguearte y luego guardar con:
	# await context.storage_state(path='data/storage/facebook_storage_state.json')
	"storage_state_path": "data/storage/facebook_storage_state.json",
	# Parámetros de scroll y límites
	"scroll": {
		"max_scrolls": 20,
		"pause_ms": 1500,
		"max_no_new": 6
	},
}

