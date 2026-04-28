export const DEFAULT_PERMISSIONS = {
	workspace: {
		models: true,
		knowledge: true,
		prompts: true,
		tools: true,
		skills: true,
		models_import: true,
		models_export: true,
		prompts_import: true,
		prompts_export: true,
		tools_import: true,
		tools_export: true
	},
	sharing: {
		models: true,
		public_models: true,
		knowledge: true,
		public_knowledge: true,
		prompts: true,
		public_prompts: true,
		tools: true,
		public_tools: true,
		skills: true,
		public_skills: true
	},
	access_grants: {
		allow_users: true
	},
	chat: {
		controls: true,
		valves: true,
		system_prompt: true,
		params: true,
		file_upload: true,
		web_upload: true,
		delete: true,
		delete_message: true,
		continue_response: true,
		regenerate_response: true,
		rate_response: true,
		edit: true,
		share: true,
		export: true,
		stt: true,
		tts: true,
		call: true,
		multiple_models: true,
		temporary: true,
		temporary_enforced: false
	},
	features: {
		api_keys: true,
		folders: true,
		direct_tool_servers: true,
		web_search: true,
		image_generation: true,
		code_interpreter: true,
		memories: true
	}
} as const;
