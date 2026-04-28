<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, onMount, getContext, tick } from 'svelte';
	import { v4 as uuidv4 } from 'uuid';
	import { getModels as _getModels } from '$lib/apis';

	const dispatch = createEventDispatcher();
	const i18n = getContext('i18n');

	import { models, settings, user, terminalServers } from '$lib/stores';
	import { getTerminalServers } from '$lib/apis/terminal';
	import { WEBUI_API_BASE_URL } from '$lib/constants';

	import Switch from '$lib/components/common/Switch.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';
	import Cog6 from '$lib/components/icons/Cog6.svelte';
	import WrenchAlt from '$lib/components/icons/WrenchAlt.svelte';

	import AddToolServerModal from '$lib/components/AddToolServerModal.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

	import {
		getToolServerConnections,
		setToolServerConnections,
		getTerminalServerConnections,
		setTerminalServerConnections
	} from '$lib/apis/configs';

	export let saveSettings: Function;

	let servers = null;

	let showAddConnectionModal = false;
	let showEditConnectionModal = false;
	let editConnectionIdx = -1;

	let showDeleteConfirmDialog = false;
	let deleteConnectionIdx = -1;

	// Terminal server admin connections
	let terminalConnections = [];

	const addConnectionHandler = async (server) => {
		servers = [...servers, server];
		await updateHandler();
	};

	const editConnectionHandler = async (server) => {
		if (editConnectionIdx >= 0) {
			servers = servers.map((s, i) => (i === editConnectionIdx ? server : s));
			await updateHandler();
		}
	};

	const deleteConnection = async (idx) => {
		servers = servers.filter((_, i) => i !== idx);
		await updateHandler();
	};

	const toggleConnection = async (idx, enable) => {
		servers = servers.map((s, i) => {
			if (i !== idx) return s;
			const next = { ...s };
			next.config = { ...(next.config ?? {}), enable };
			return next;
		});
		await updateHandler();
	};

	const updateHandler = async () => {
		const res = await setToolServerConnections(localStorage.token, {
			TOOL_SERVER_CONNECTIONS: servers
		}).catch((err) => {
			toast.error($i18n.t('Failed to save connections'));
			return null;
		});

		if (res) {
			toast.success($i18n.t('Connections saved successfully'));
		}
	};

	const saveTerminalServers = async () => {
		const res = await setTerminalServerConnections(localStorage.token, {
			TERMINAL_SERVER_CONNECTIONS: terminalConnections
		}).catch((err) => {
			toast.error($i18n.t('Failed to save terminal servers'));
			return null;
		});

		if (res) {
			toast.success($i18n.t('Terminal servers saved'));

			const existingDirectTerminals = ($terminalServers ?? []).filter((t) => !t.id);
			const systemTerminals = await getTerminalServers(localStorage.token);
			const systemEntries = systemTerminals.map((t) => ({
				id: t.id,
				url: `${WEBUI_API_BASE_URL}/terminals/${t.id}`,
				name: t.name,
				key: localStorage.token
			}));
			terminalServers.set([...existingDirectTerminals, ...systemEntries]);
		}
	};

	onMount(async () => {
		const res = await getToolServerConnections(localStorage.token);
		servers = res.TOOL_SERVER_CONNECTIONS;

		try {
			const terminalRes = await getTerminalServerConnections(localStorage.token);
			if (terminalRes?.TERMINAL_SERVER_CONNECTIONS) {
				terminalConnections = terminalRes.TERMINAL_SERVER_CONNECTIONS;
			}
		} catch {
			// Not configured yet
		}
	});
</script>

<AddToolServerModal bind:show={showAddConnectionModal} onSubmit={addConnectionHandler} />

<AddToolServerModal
	edit
	bind:show={showEditConnectionModal}
	connection={editConnectionIdx >= 0 ? servers?.[editConnectionIdx] ?? null : null}
	onSubmit={editConnectionHandler}
	onDelete={() => {
		showDeleteConfirmDialog = true;
		deleteConnectionIdx = editConnectionIdx;
	}}
/>

<ConfirmDialog
	bind:show={showDeleteConfirmDialog}
	on:confirm={() => {
		if (deleteConnectionIdx >= 0) {
			deleteConnection(deleteConnectionIdx);
			deleteConnectionIdx = -1;
			showEditConnectionModal = false;
		}
	}}
/>

<div class="flex flex-col h-full justify-between text-sm">
	<div class="overflow-y-scroll scrollbar-hidden h-full">
		{#if servers !== null}
			{#if servers.length === 0}
				<!-- Empty state -->
				<div class="flex flex-col items-center justify-center h-full min-h-[300px] text-center">
					<div class="text-gray-400 dark:text-gray-500 mb-6 text-base">
						{$i18n.t('No tool server connections configured.')}
					</div>

					<button
						class="flex items-center justify-center w-20 h-20 rounded-2xl border-2 border-dashed border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500 hover:bg-gray-50 dark:hover:bg-gray-800 transition-all duration-200 group"
						on:click={() => {
							showAddConnectionModal = true;
						}}
						type="button"
					>
						<Plus
							className="size-10 text-gray-400 dark:text-gray-500 group-hover:text-gray-600 dark:group-hover:text-gray-300 transition-colors"
						/>
					</button>

					<div class="text-xs text-gray-400 dark:text-gray-500 mt-3">
						{$i18n.t('Click to add a tool server connection')}
					</div>

					<div class="text-xs text-gray-400 dark:text-gray-500 mt-2 max-w-xs">
						{$i18n.t('Connect to your own OpenAPI compatible external tool servers.')}
					</div>
				</div>
			{:else}
				<!-- Connection list -->
				<div class="mb-3.5">
					<div class="flex justify-between items-center mt-0.5 mb-2.5 gap-2">
						<div class="text-base font-medium shrink-0">
							{$i18n.t('Integrations')}
						</div>

						<div class="flex items-center gap-1.5 min-w-0">
							<Tooltip
								content={$i18n.t(
									'These connections are shared across all users in this workspace.'
								)}
							>
								<div
									class="flex items-center gap-1 text-xs text-gray-400 dark:text-gray-500 cursor-help truncate"
								>
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 20 20"
										fill="currentColor"
										class="size-3.5 shrink-0"
										aria-hidden="true"
									>
										<path
											fill-rule="evenodd"
											d="M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Zm-7-4a1 1 0 1 1-2 0 1 1 0 0 1 2 0ZM9 9a.75.75 0 0 0 0 1.5h.253a.25.25 0 0 1 .244.304l-.459 2.066A1.75 1.75 0 0 0 10.747 15H11a.75.75 0 0 0 0-1.5h-.253a.25.25 0 0 1-.244-.304l.459-2.066A1.75 1.75 0 0 0 9.253 9H9Z"
											clip-rule="evenodd"
										/>
									</svg>
									<span class="truncate">{$i18n.t('Shared with all users')}</span>
								</div>
							</Tooltip>

							<Tooltip content={$i18n.t('Add Connection')}>
								<button
									class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-850 transition shrink-0"
									on:click={() => {
										showAddConnectionModal = true;
									}}
									type="button"
								>
									<Plus className="size-4" />
								</button>
							</Tooltip>
						</div>
					</div>

					<hr class="border-gray-100/30 dark:border-gray-850/30 my-2" />

					<div class="flex flex-col gap-2 mt-2">
						{#each servers as server, idx (idx)}
							{@const enabled = server?.config?.enable ?? true}
							{@const displayName = server?.info?.name || server?.url || $i18n.t('No URL')}
							{@const displayId = server?.info?.id ?? ''}
							{@const typeLabel = server?.type === 'mcp' ? 'MCP' : 'OpenAPI'}
							<div
								class="flex items-center gap-3 px-3 py-2.5 rounded-xl border border-gray-100 dark:border-gray-800 {!enabled
									? 'opacity-50'
									: ''}"
							>
								<div
									class="shrink-0 size-8 rounded-lg bg-gray-50 dark:bg-gray-850 flex items-center justify-center text-gray-500 dark:text-gray-400"
								>
									<WrenchAlt className="size-4" />
								</div>

								<div class="flex-1 min-w-0">
									<div class="flex items-center gap-1.5 min-w-0">
										<div class="text-sm font-medium truncate">{displayName}</div>
										{#if displayId}
											<div
												class="text-xs text-gray-400 dark:text-gray-500 font-mono truncate"
											>
												{displayId}
											</div>
										{/if}
									</div>
									<div
										class="text-xs text-gray-400 dark:text-gray-500 mt-0.5 flex items-center gap-1.5"
									>
										<span
											class="px-1.5 py-px rounded-md bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 text-[10px] font-medium uppercase tracking-wide shrink-0"
										>
											{typeLabel}
										</span>
										<span class="truncate">{server?.url || ''}</span>
									</div>
								</div>

								<div class="flex items-center gap-1 shrink-0">
									<Tooltip content={$i18n.t('Configure')}>
										<button
											class="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-850 transition"
											on:click={() => {
												editConnectionIdx = idx;
												showEditConnectionModal = true;
											}}
											type="button"
										>
											<Cog6 className="size-4" />
										</button>
									</Tooltip>

									<Tooltip content={enabled ? $i18n.t('Enabled') : $i18n.t('Disabled')}>
										<Switch
											state={enabled}
											on:change={() => {
												toggleConnection(idx, !enabled);
											}}
										/>
									</Tooltip>

									<Tooltip content={$i18n.t('Delete')}>
										<button
											class="p-1.5 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 text-gray-500 hover:text-red-600 dark:hover:text-red-400 transition"
											on:click={() => {
												deleteConnectionIdx = idx;
												showDeleteConfirmDialog = true;
											}}
											type="button"
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												viewBox="0 0 20 20"
												fill="currentColor"
												class="size-4"
											>
												<path
													fill-rule="evenodd"
													d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022 1.005 11.07A2.611 2.611 0 007.63 19.5h4.74c1.38 0 2.529-1.08 2.61-2.48l1.006-11.07.148.022a.75.75 0 10.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z"
													clip-rule="evenodd"
												/>
											</svg>
										</button>
									</Tooltip>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}
		{:else}
			<div class="flex h-full justify-center">
				<div class="my-auto">
					<Spinner className="size-6" />
				</div>
			</div>
		{/if}
	</div>
</div>
