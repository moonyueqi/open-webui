<script lang="ts">
	import { onMount, onDestroy, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import { goto } from '$app/navigation';

	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	import localizedFormat from 'dayjs/plugin/localizedFormat';

	import { WEBUI_NAME, socket } from '$lib/stores';

	import {
		updateAutomationById,
		toggleAutomationById,
		runAutomationById,
		deleteAutomationById,
		getAutomationById,
		getAutomationRuns,
		type AutomationForm,
		type AutomationResponse,
		type AutomationRunModel
	} from '$lib/apis/automations';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte';
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte';
	import InputVariablesModal from '$lib/components/chat/MessageInput/InputVariablesModal.svelte';

	import ScheduleDropdown from '$lib/components/automations/ScheduleDropdown.svelte';
	import ModelDropdown from '$lib/components/automations/ModelDropdown.svelte';
	import ToolsDropdown from '$lib/components/automations/ToolsDropdown.svelte';
	import SkillsDropdown from '$lib/components/automations/SkillsDropdown.svelte';
	import PromptsDropdown from '$lib/components/automations/PromptsDropdown.svelte';

	import { extractInputVariables, validateInputVariables } from '$lib/utils';

	dayjs.extend(relativeTime);
	dayjs.extend(localizedFormat);

	const i18n = getContext('i18n');

	export let automation: AutomationResponse;

	let name = '';
	let prompt = '';
	let model_id = '';
	let tool_ids: string[] = [];
	let skill_ids: string[] = [];
	let deep_thinking = false;
	let is_active = true;

	let loading = false;
	let saving = false;
	let showDeleteConfirm = false;

	let runs: AutomationRunModel[] = [];
	let runsLoading = false;
	let hasMoreRuns = true;
	let runsPage = 0;
	let isDirty = false;

	let scheduleDropdown: ScheduleDropdown;

	// System-level template variables resolved at runtime on the backend.
	// Keep them in the prompt and DON'T ask the user to fill them in.
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

			const pipeIdx = trimmed.indexOf('|');
			if (pipeIdx !== -1) {
				const key = trimmed.slice(0, pipeIdx).trim();
				return Object.prototype.hasOwnProperty.call(values, key)
					? String(values[key] ?? '')
					: full;
			}

			if (Object.prototype.hasOwnProperty.call(values, trimmed)) {
				return String(values[trimmed] ?? '');
			}

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

	const formatRunTime = (ts: number): string => {
		const now = Date.now();
		const diff = now - ts / 1_000_000;

		const seconds = Math.floor(diff / 1000);
		const minutes = Math.floor(seconds / 60);
		const hours = Math.floor(minutes / 60);
		const days = Math.floor(hours / 24);
		const weeks = Math.floor(days / 7);
		const years = Math.floor(days / 365);

		if (years > 0) return $i18n.t('{{COUNT}}y', { COUNT: years, context: 'time_ago' });
		if (weeks > 0) return $i18n.t('{{COUNT}}w', { COUNT: weeks, context: 'time_ago' });
		if (days > 0) return $i18n.t('{{COUNT}}d', { COUNT: days, context: 'time_ago' });
		if (hours > 0) return $i18n.t('{{COUNT}}h', { COUNT: hours, context: 'time_ago' });
		if (minutes > 0) return $i18n.t('{{COUNT}}m', { COUNT: minutes, context: 'time_ago' });
		return $i18n.t('1m', { context: 'time_ago' });
	};

	const formatNextRun = (ts: number | null): string => {
		if (!ts) return $i18n.t('Not scheduled');
		const d = dayjs(ts / 1_000_000);
		if (d.isSame(dayjs(), 'day')) return `${$i18n.t('Today at')} ${d.format('LT')}`;
		return d.format('L LT');
	};

	const saveHandler = async () => {
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

		saving = true;
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
			const updated = await updateAutomationById(localStorage.token, automation.id, form);
			if (updated) {
				automation = updated;
				isDirty = false;
				toast.success($i18n.t('Automation updated'));
			}
		} catch (e: any) {
			toast.error(e?.detail ?? `${e}` ?? 'Failed to save');
		} finally {
			saving = false;
		}
	};

	const toggleHandler = async () => {
		const res = await toggleAutomationById(localStorage.token, automation.id).catch((err) => {
			toast.error(`${err}`);
			return null;
		});
		if (res) {
			is_active = res.is_active;
			automation = res;
		}
	};

	const runNowHandler = async () => {
		loading = true;
		const res = await runAutomationById(localStorage.token, automation.id).catch((err) => {
			toast.error(`${err}`);
			return null;
		});
		if (res) {
			toast.success($i18n.t('Automation triggered'));
		}
		loading = false;
	};

	// Real-time refresh: backend emits `automation:result` to room `user:<id>`
	// after every run (manual or scheduled). Keep logs / next_runs in sync
	// without forcing the user to refresh the page.
	const onAutomationResult = async (data: { automation_id?: string }) => {
		if (!data || data.automation_id !== automation.id) return;
		await loadRuns(false);
		const fresh = await getAutomationById(localStorage.token, automation.id).catch(() => null);
		if (fresh) automation = fresh;
	};

	const deleteHandler = async () => {
		const res = await deleteAutomationById(localStorage.token, automation.id).catch((err) => {
			toast.error(`${err}`);
			return null;
		});
		if (res) {
			toast.success($i18n.t(`Deleted {{name}}`, { name: automation.name }));
			goto('/automations');
		}
	};

	const loadRuns = async (loadMore = false) => {
		if (runsLoading || (!hasMoreRuns && loadMore)) return;

		runsLoading = true;

		if (!loadMore) {
			runsPage = 0;
			hasMoreRuns = true;
		}

		try {
			const fetchedRuns =
				(await getAutomationRuns(localStorage.token, automation.id, runsPage * 50, 50)) ?? [];
			if (loadMore) {
				runs = [...runs, ...fetchedRuns];
			} else {
				runs = fetchedRuns;
			}

			if (fetchedRuns.length < 50) {
				hasMoreRuns = false;
			}
			runsPage++;
		} catch {
			if (!loadMore) runs = [];
		}
		runsLoading = false;
	};

	const markDirty = () => {
		isDirty = true;
	};

	const onScroll = (e: Event) => {
		const target = e.target as HTMLElement;
		if (target.scrollTop + target.clientHeight >= target.scrollHeight - 50) {
			if (!runsLoading && hasMoreRuns) {
				loadRuns(true);
			}
		}
	};

	const appendPromptContent = (content: string) => {
		prompt = prompt && prompt.trim() ? `${prompt.trimEnd()}\n\n${content}` : content;
		markDirty();
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

	onMount(async () => {
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

		await loadRuns();

		$socket?.on('automation:result', onAutomationResult);
	});

	onDestroy(() => {
		$socket?.off('automation:result', onAutomationResult);
	});
</script>

<svelte:head>
	<title>{name || $i18n.t('Automation')} • {$WEBUI_NAME}</title>
</svelte:head>

<InputVariablesModal
	bind:show={showInputVariablesModal}
	variables={inputVariables}
	onSave={(values) => inputVariablesCallback(values)}
/>

<DeleteConfirmDialog
	bind:show={showDeleteConfirm}
	title={$i18n.t('Delete automation?')}
	on:confirm={deleteHandler}
>
	<div class="text-sm text-gray-500 truncate">
		{$i18n.t('This will delete')} <span class="">{automation.name}</span>.
	</div>
</DeleteConfirmDialog>

<div class="flex flex-col w-full h-screen max-h-[100dvh] max-w-full">
	<div class="flex-1 max-h-full flex flex-col pt-4 pb-5 px-4 md:px-6">
		<!-- Header -->
		<div class="flex items-center justify-between gap-4 shrink-0 mb-3 px-1">
			<div class="flex items-center gap-3 flex-1 min-w-0">
				<Tooltip content={$i18n.t('Back')}>
					<button
						class="p-1.5 hover:bg-black/5 dark:hover:bg-white/5 rounded-lg transition shrink-0"
						aria-label={$i18n.t('Back')}
						on:click={() => goto('/automations')}
						type="button"
					>
						<ChevronLeft strokeWidth="2.5" />
					</button>
				</Tooltip>

				<div
					class="flex items-center justify-center w-9 h-9 rounded-xl shrink-0 {is_active
						? 'bg-sky-500/10 dark:bg-sky-500/15'
						: 'bg-gray-100 dark:bg-gray-800'}"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						fill="none"
						viewBox="0 0 24 24"
						stroke-width="1.5"
						stroke="currentColor"
						class="size-5 {is_active
							? 'text-sky-600 dark:text-sky-400'
							: 'text-gray-400 dark:text-gray-500'}"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
						/>
					</svg>
				</div>

				<input
					class="text-xl font-semibold w-full bg-transparent outline-hidden min-w-0"
					placeholder={$i18n.t('Automation Name')}
					bind:value={name}
					on:input={markDirty}
				/>
			</div>

			<div class="flex items-center gap-1.5 shrink-0">
				<Tooltip content={$i18n.t('Delete')}>
					<button
						class="px-3 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-600 hover:text-red-600 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-300 dark:hover:text-red-400 transition font-medium text-sm flex items-center gap-1.5 border border-gray-200/60 dark:border-gray-700/60"
						on:click={() => (showDeleteConfirm = true)}
						type="button"
						aria-label={$i18n.t('Delete')}
					>
						<GarbageBin />
					</button>
				</Tooltip>

				<button
					class="px-3 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition font-medium text-sm flex items-center gap-1.5 border border-gray-200/60 dark:border-gray-700/60 disabled:opacity-50"
					on:click={runNowHandler}
					type="button"
					disabled={loading}
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						viewBox="0 0 20 20"
						fill="currentColor"
						class="size-3.5"
					>
						<path
							d="M6.3 2.84A1.5 1.5 0 0 0 4 4.11v11.78a1.5 1.5 0 0 0 2.3 1.27l9.344-5.891a1.5 1.5 0 0 0 0-2.538L6.3 2.841Z"
						/>
					</svg>
					<div class="hidden md:block text-xs">{$i18n.t('Run now')}</div>
					{#if loading}
						<Spinner className="size-3" />
					{/if}
				</button>

				{#if isDirty}
					<button
						class="px-3 py-2 rounded-xl bg-black hover:bg-gray-900 text-white dark:bg-white dark:hover:bg-gray-100 dark:text-black transition font-medium text-sm flex items-center gap-1.5 disabled:opacity-50"
						on:click={saveHandler}
						disabled={saving}
						type="button"
					>
						<div class="text-xs">{$i18n.t('Save')}</div>
						{#if saving}
							<Spinner className="size-3" />
						{/if}
					</button>
				{/if}
			</div>
		</div>

		<!-- Content Segment: Independent Scrolling Columns based on PromptEditor -->
		<div class="flex flex-col md:flex-row gap-4 flex-1 overflow-hidden pb-2">
			<!-- Main Input Column -->
			<div class="flex-1 flex flex-col min-h-0 overflow-hidden">
				<div class="flex items-center justify-between mb-2 shrink-0 px-1">
					<div class="text-gray-700 dark:text-gray-300 text-sm font-semibold">
						{$i18n.t('Instructions')}
					</div>
					<PromptsDropdown side="bottom" align="end" onSelect={insertPrompt} />
				</div>
				<div class="relative flex-1 min-h-0">
					<div
						class="bg-white dark:bg-gray-900 rounded-2xl p-4 border border-gray-200/60 dark:border-gray-800/60 shadow-sm h-full"
					>
						<textarea
							class="w-full h-full text-sm bg-transparent outline-hidden resize-none placeholder:text-gray-300 dark:placeholder:text-gray-700"
							bind:value={prompt}
							on:input={markDirty}
							placeholder={$i18n.t('Enter the prompt instructions for this automation...')}
						/>
					</div>
				</div>
			</div>

			<!-- Sidebar Configuration Column -->
			<div
				class="hidden md:flex w-full md:w-80 shrink-0 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-800/60 shadow-sm flex-col overflow-hidden"
			>
				<!-- Configuration section -->
				<div class="px-4 pt-4 pb-3 shrink-0">
					<div class="text-gray-700 dark:text-gray-300 text-sm font-semibold mb-3">
						{$i18n.t('Configuration')}
					</div>
					<div class="space-y-2">
						<!-- Schedule -->
						<div class="flex items-center justify-between text-xs min-h-7">
							<span class="text-gray-500 dark:text-gray-400">{$i18n.t('Repeats')}</span>
							<ScheduleDropdown
								bind:this={scheduleDropdown}
								side="bottom"
								align="end"
								onChange={markDirty}
							/>
						</div>

						<!-- Model -->
						<div class="flex items-center justify-between text-xs min-h-7">
							<span class="text-gray-500 dark:text-gray-400">{$i18n.t('Model')}</span>
							<ModelDropdown bind:model_id side="bottom" align="end" onChange={markDirty} />
						</div>

						<!-- Tools -->
						<div class="flex items-center justify-between text-xs min-h-7">
							<span class="text-gray-500 dark:text-gray-400">{$i18n.t('Tools')}</span>
							<ToolsDropdown bind:tool_ids side="bottom" align="end" onChange={markDirty} />
						</div>

						<!-- Skills -->
						<div class="flex items-center justify-between text-xs min-h-7">
							<span class="text-gray-500 dark:text-gray-400">{$i18n.t('Skills')}</span>
							<SkillsDropdown bind:skill_ids side="bottom" align="end" onChange={markDirty} />
						</div>

						<!-- Deep Thinking -->
						<div class="flex items-center justify-between text-xs min-h-7">
							<Tooltip
								content={$i18n.t(
									'Some thinking-only models (e.g. Qwen3 Thinking series) require this to be enabled. If the model returns "enable_thinking restricted to True", turn this on.'
								)}
								placement="top"
							>
								<span
									id="deep-thinking-label"
									class="text-gray-500 dark:text-gray-400 inline-flex items-center gap-1 cursor-help"
								>
									{$i18n.t('Deep Thinking')}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 20 20"
										fill="currentColor"
										class="size-3 text-gray-400 dark:text-gray-500"
									>
										<path
											fill-rule="evenodd"
											d="M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Zm-7-4a1 1 0 1 1-2 0 1 1 0 0 1 2 0ZM9 9a.75.75 0 0 0 0 1.5h.253a.25.25 0 0 1 .244.304l-.459 2.066A1.75 1.75 0 0 0 10.747 15H11a.75.75 0 0 0 0-1.5h-.253a.25.25 0 0 1-.244-.304l.459-2.066A1.75 1.75 0 0 0 9.253 9H9Z"
											clip-rule="evenodd"
										/>
									</svg>
								</span>
							</Tooltip>
							<Switch
								bind:state={deep_thinking}
								on:change={markDirty}
								ariaLabelledbyId="deep-thinking-label"
							/>
						</div>
					</div>
				</div>

				<div class="mx-4 border-t border-gray-100 dark:border-gray-800/80"></div>

				<!-- Status section -->
				<div class="px-4 pt-3 pb-3 shrink-0">
					<div class="text-gray-700 dark:text-gray-300 text-sm font-semibold mb-3">
						{$i18n.t('Status')}
					</div>
					<div class="space-y-2">
						<div class="flex items-center justify-between text-xs min-h-7">
							<span class="text-gray-500 dark:text-gray-400">{$i18n.t('State')}</span>
							<span
								class="flex items-center gap-1.5 text-xs {is_active
									? 'text-emerald-700 dark:text-emerald-400'
									: 'text-gray-600 dark:text-gray-400'}"
							>
								<span
									class="inline-block size-1.5 rounded-full {is_active
										? 'bg-emerald-500'
										: 'bg-gray-400'}"
								></span>
								{is_active ? $i18n.t('Enabled') : $i18n.t('Paused')}
							</span>
						</div>

						<div class="flex items-center justify-between text-xs min-h-7">
							<span class="text-gray-500 dark:text-gray-400">{$i18n.t('Next run')}</span>
							<span class="text-gray-700 dark:text-gray-300"
								>{formatNextRun(automation.next_runs?.[0] ?? automation.next_run_at)}</span
							>
						</div>

						<div class="flex items-center justify-between text-xs min-h-7">
							<span class="text-gray-500 dark:text-gray-400">{$i18n.t('Last ran')}</span>
							<span class="text-gray-700 dark:text-gray-300"
								>{automation.last_run_at
									? formatNextRun(automation.last_run_at)
									: $i18n.t('Never')}</span
							>
						</div>
					</div>
				</div>

				<div class="mx-4 border-t border-gray-100 dark:border-gray-800/80"></div>

				<!-- Execution Logs section -->
				<div class="flex-1 flex flex-col min-h-0 px-4 pt-3 pb-4">
					<div class="text-gray-700 dark:text-gray-300 text-sm font-semibold mb-2 shrink-0">
						{$i18n.t('Execution Logs')}
					</div>
					<div class="flex-1 overflow-y-auto scrollbar-hidden w-full -mx-2" on:scroll={onScroll}>
						{#if runsLoading && runs.length === 0}
							<div class="flex justify-center py-4">
								<Spinner className="size-4" />
							</div>
						{:else if runs.length === 0}
							<div class="text-xs text-gray-400 py-4 px-2 tabular-nums">
								{$i18n.t('No execution logs available yet')}
							</div>
						{:else}
							<div class="space-y-0.5 w-full">
								{#each runs as run (run.id)}
									<button
										class="w-full text-left flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-gray-100/80 dark:hover:bg-gray-850/80 transition-colors {run.chat_id
											? 'cursor-pointer'
											: 'cursor-default'}"
										on:click={() => {
											if (run.chat_id) goto(`/c/${run.chat_id}`);
										}}
										type="button"
									>
										<div class="shrink-0 flex items-center justify-center">
											{#if run.status === 'success'}
												<svg
													xmlns="http://www.w3.org/2000/svg"
													viewBox="0 0 20 20"
													fill="currentColor"
													class="size-3 text-emerald-500"
													><path
														fill-rule="evenodd"
														d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
														clip-rule="evenodd"
													/></svg
												>
											{:else if run.status === 'error'}
												<svg
													xmlns="http://www.w3.org/2000/svg"
													viewBox="0 0 20 20"
													fill="currentColor"
													class="size-3 text-red-500"
													><path
														fill-rule="evenodd"
														d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
														clip-rule="evenodd"
													/></svg
												>
											{:else}
												<svg
													xmlns="http://www.w3.org/2000/svg"
													viewBox="0 0 20 20"
													fill="currentColor"
													class="size-3 text-blue-500"
													><path
														d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-13a.75.75 0 00-1.5 0v5c0 .414.336.75.75.75h4a.75.75 0 000-1.5h-3.25V5z"
													/></svg
												>
											{/if}
										</div>
										<div class="flex-1 min-w-0">
											<div class="text-xs text-gray-800 dark:text-gray-200 truncate">
												{automation.name}
											</div>
										</div>
										<span class="shrink-0 text-[10px] text-gray-500 font-mono"
											>{formatRunTime(run.created_at)}</span
										>
									</button>
								{/each}

								{#if runsLoading && runs.length > 0}
									<div class="flex justify-center py-4">
										<Spinner className="size-4" />
									</div>
								{/if}
							</div>
						{/if}
					</div>
				</div>
			</div>
		</div>
	</div>
</div>
