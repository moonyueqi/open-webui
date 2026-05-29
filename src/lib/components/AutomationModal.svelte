<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import InputVariablesModal from '$lib/components/chat/MessageInput/InputVariablesModal.svelte';

	import ScheduleDropdown from '$lib/components/automations/ScheduleDropdown.svelte';
	import ModelDropdown from '$lib/components/automations/ModelDropdown.svelte';
	import ToolsDropdown from '$lib/components/automations/ToolsDropdown.svelte';
	import SkillsDropdown from '$lib/components/automations/SkillsDropdown.svelte';
	import PromptsDropdown from '$lib/components/automations/PromptsDropdown.svelte';

	import { extractInputVariables, validateInputVariables } from '$lib/utils';

	import {
		createAutomation,
		updateAutomationById,
		type AutomationForm,
		type AutomationResponse
	} from '$lib/apis/automations';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let show = false;
	export let automation: AutomationResponse | null = null;

	let name = '';
	let prompt = '';
	let model_id = '';
	let tool_ids: string[] = [];
	let skill_ids: string[] = [];
	let deep_thinking = false;
	let is_active = true;

	let loading = false;

	// Schedule dropdown ref
	let scheduleDropdown: ScheduleDropdown;

	// System-level template variables that are resolved at runtime on the backend.
	// We deliberately keep them in the prompt and DON'T ask the user to fill them in.
	const SYSTEM_VARIABLES = new Set([
		'CLIPBOARD',
		'USER_LOCATION',
		'USER_NAME',
		'USER_EMAIL',
		'USER_BIO',
		'USER_GENDER',
		'USER_BIRTH_DATE',
		'USER_AGE',
		'USER_LANGUAGE',
		'CURRENT_DATE',
		'CURRENT_TIME',
		'CURRENT_DATETIME',
		'CURRENT_TIMEZONE',
		'CURRENT_WEEKDAY'
	]);

	// Input variables modal state
	let showInputVariablesModal = false;
	let inputVariables: Record<string, any> = {};
	let pendingPromptContent = '';
	let inputVariablesCallback: (values: Record<string, any>) => void = () => {};

	const replacePromptVariables = (text: string, values: Record<string, any>): string => {
		// Match any "{{ ... }}" body, then derive the variable name based on the
		// supported syntaxes:
		//   1. Pipe syntax:        {{name | type=...}}
		//   2. Shorthand select:   {{name：opt1、opt2、opt3}}  (Chinese colon or ':')
		//   3. Plain:              {{name}}
		return text.replace(/{{\s*([^}]+?)\s*}}/g, (full, body) => {
			const trimmed = body.trim();

			// Pipe syntax — name is before the first '|'.
			const pipeIdx = trimmed.indexOf('|');
			if (pipeIdx !== -1) {
				const key = trimmed.slice(0, pipeIdx).trim();
				return Object.prototype.hasOwnProperty.call(values, key)
					? String(values[key] ?? '')
					: full;
			}

			// Direct match (e.g. "{{name}}").
			if (Object.prototype.hasOwnProperty.call(values, trimmed)) {
				return String(values[trimmed] ?? '');
			}

			// Shorthand-select — name is before the first ':' or '：'.
			const colonMatch = trimmed.match(/^([^:：]+)[:：][\s\S]+$/);
			if (colonMatch) {
				const key = colonMatch[1].trim();
				if (Object.prototype.hasOwnProperty.call(values, key)) {
					return String(values[key] ?? '');
				}
			}

			return full;
		});
	};

	const submitHandler = async () => {
		if (!name.trim() || !prompt.trim() || !model_id.trim()) {
			toast.error($i18n.t('Name, prompt, and model are required'));
			return;
		}

		// Validate input-variable templates inside the prompt. Errors block
		// submission, warnings are shown but do not block.
		const issues = validateInputVariables(prompt);
		let hasError = false;
		for (const issue of issues) {
			const message = $i18n.t(issue.key, issue.params ?? {});
			if (issue.severity === 'error') {
				toast.error(message);
				hasError = true;
			} else {
				toast.warning(message);
			}
		}
		if (hasError) return;

		if (scheduleDropdown?.frequency === 'ONCE') {
			const scheduled = new Date(`${scheduleDropdown.onceDate}T${scheduleDropdown.onceTime}`);
			if (scheduled <= new Date()) {
				toast.error($i18n.t('Scheduled time must be in the future'));
				return;
			}
		}
		loading = true;
		try {
			const form: AutomationForm = {
				name: name.trim(),
				data: {
					prompt: prompt.trim(),
					model_id: model_id.trim(),
					rrule: scheduleDropdown.buildRrule(),
					...(tool_ids.length ? { tool_ids } : {}),
					...(skill_ids.length ? { skill_ids } : {}),
					deep_thinking
				},
				is_active
			};

			if (automation) {
				await updateAutomationById(localStorage.token, automation.id, form);
				toast.success($i18n.t('Automation updated'));
				show = false;
				dispatch('save', { id: automation.id });
			} else {
				const created = await createAutomation(localStorage.token, form);
				toast.success($i18n.t('Automation created'));
				show = false;
				dispatch('save', { id: created?.id });
			}
		} catch (e: any) {
			toast.error(e?.detail ?? `${e}` ?? 'Failed to save');
		} finally {
			loading = false;
		}
	};

	const appendPromptContent = (content: string) => {
		prompt = prompt && prompt.trim() ? `${prompt.trimEnd()}\n\n${content}` : content;
	};

	const insertPrompt = (content: string) => {
		if (!content) return;

		const issues = validateInputVariables(content);
		for (const issue of issues) {
			const message = $i18n.t(issue.key, issue.params ?? {});
			if (issue.severity === 'error') {
				toast.error(message);
			} else {
				toast.warning(message);
			}
		}

		const allVariables = extractInputVariables(content);
		const userVariables: Record<string, any> = {};
		for (const key of Object.keys(allVariables)) {
			if (!SYSTEM_VARIABLES.has(key)) {
				userVariables[key] = allVariables[key];
			}
		}

		if (Object.keys(userVariables).length === 0) {
			appendPromptContent(content);
			return;
		}

		pendingPromptContent = content;
		inputVariables = userVariables;
		inputVariablesCallback = (values) => {
			const resolved = replacePromptVariables(pendingPromptContent, values);
			appendPromptContent(resolved);
			pendingPromptContent = '';
			inputVariables = {};
		};
		showInputVariablesModal = true;
	};

	const init = async () => {
		if (automation) {
			name = automation.name;
			prompt = automation.data.prompt;
			model_id = automation.data.model_id;
			tool_ids = [...(automation.data.tool_ids ?? [])];
			skill_ids = [...(automation.data.skill_ids ?? [])];
			deep_thinking = automation.data.deep_thinking ?? false;
			is_active = automation.is_active;
			if (scheduleDropdown) {
				scheduleDropdown.parseRrule(automation.data.rrule);
			}
		} else {
			name = '';
			prompt = '';
			model_id = '';
			tool_ids = [];
			skill_ids = [];
			deep_thinking = false;
			is_active = true;
		}
	};

	$: if (show) {
		init();
	}
</script>

<Modal size="md" bind:show>
	<div>
		<!-- Header -->
		<div class="flex items-center justify-between gap-2 dark:text-gray-100 px-5 pt-4 pb-2">
			<div class="flex items-center gap-3 flex-1 min-w-0">
				<div
					class="flex items-center justify-center w-9 h-9 rounded-xl bg-sky-500/10 dark:bg-sky-500/15 shrink-0"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						fill="none"
						viewBox="0 0 24 24"
						stroke-width="1.5"
						stroke="currentColor"
						class="size-5 text-sky-600 dark:text-sky-400"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
						/>
					</svg>
				</div>
				<input
					class="w-full text-lg font-semibold bg-transparent outline-hidden font-primary placeholder:text-gray-300 dark:placeholder:text-gray-700"
					type="text"
					bind:value={name}
					placeholder={$i18n.t('Automation title')}
				/>
			</div>
			<button
				class="self-center shrink-0 p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition"
				aria-label={$i18n.t('Close')}
				on:click={() => (show = false)}
			>
				<XMark className="size-5" />
			</button>
		</div>

		<!-- Prompt -->
		<div class="px-5 pb-2 pt-4">
			<textarea
				class="w-full text-sm bg-gray-50 dark:bg-gray-850/50 border border-gray-200 dark:border-gray-800 rounded-xl px-3.5 py-3 outline-hidden focus:border-gray-300 dark:focus:border-gray-700 placeholder:text-gray-400 dark:placeholder:text-gray-600 resize-none min-h-[8rem] transition"
				bind:value={prompt}
				rows={5}
				placeholder={$i18n.t('Enter instructions here.')}
			/>
		</div>

		<!-- Bottom toolbar -->
		<div
			class="flex items-center justify-between px-4 pb-3.5 pt-1 gap-2 border-t border-gray-100 dark:border-gray-850 mt-2"
		>
			<div class="flex items-center gap-0.5 flex-wrap flex-1 min-w-0 pt-2">
				<ScheduleDropdown bind:this={scheduleDropdown} side="top" align="start" />

				<ModelDropdown bind:model_id side="top" align="start" />

				<PromptsDropdown side="top" align="start" onSelect={insertPrompt} />

				<ToolsDropdown bind:tool_ids side="top" align="start" />

				<SkillsDropdown bind:skill_ids side="top" align="start" />
			</div>

			<div class="flex items-center gap-1.5 shrink-0 pt-2">
				<button
					class="px-3 py-2 text-xs font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-800 transition"
					type="button"
					on:click={() => (show = false)}
				>
					{$i18n.t('Cancel')}
				</button>
				<button
					class="px-3 py-2 text-xs font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-xl flex items-center gap-1.5 disabled:opacity-50 {loading
						? 'cursor-not-allowed'
						: ''}"
					on:click={submitHandler}
					type="button"
					disabled={loading}
				>
					{automation ? $i18n.t('Save') : $i18n.t('Create')}
					{#if loading}
						<span class="shrink-0"><Spinner className="size-3" /></span>
					{/if}
				</button>
			</div>
		</div>
	</div>
</Modal>

<InputVariablesModal
	bind:show={showInputVariablesModal}
	variables={inputVariables}
	onSave={(values) => inputVariablesCallback(values)}
/>
