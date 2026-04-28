<script lang="ts">
	import dayjs from 'dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	dayjs.extend(relativeTime);

	import { toast } from 'svelte-sonner';
	import fileSaver from 'file-saver';
	const { saveAs } = fileSaver;

	import { onMount, getContext, tick, onDestroy } from 'svelte';
	const i18n = getContext('i18n');

	import { WEBUI_NAME, config, tools as _tools, user } from '$lib/stores';

	import { goto } from '$app/navigation';
	import {
		createNewTool,
		loadToolByUrl,
		deleteToolById,
		exportTools,
		getToolById,
		getToolList,
		getTools
	} from '$lib/apis/tools';
	import { capitalizeFirstLetter } from '$lib/utils';

	import Tooltip from '../common/Tooltip.svelte';
	import ConfirmDialog from '../common/ConfirmDialog.svelte';
	import ToolMenu from './Tools/ToolMenu.svelte';
	import EllipsisHorizontal from '../icons/EllipsisHorizontal.svelte';
	import ValvesModal from './common/ValvesModal.svelte';
	import ManifestModal from './common/ManifestModal.svelte';
	import Heart from '../icons/Heart.svelte';
	import DeleteConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import GarbageBin from '../icons/GarbageBin.svelte';
	import Search from '../icons/Search.svelte';
	import Plus from '../icons/Plus.svelte';
	import ChevronRight from '../icons/ChevronRight.svelte';
	import Spinner from '../common/Spinner.svelte';
	import XMark from '../icons/XMark.svelte';
	import AddToolMenu from './Tools/AddToolMenu.svelte';
	import ImportModal from '../ImportModal.svelte';
	import ViewSelector from './common/ViewSelector.svelte';
	import Badge from '$lib/components/common/Badge.svelte';

	let shiftKey = false;
	let loaded = false;

	let toolsImportInputElement: HTMLInputElement;
	let importFiles;

	let showConfirm = false;
	let query = '';
	let searchDebounceTimer: ReturnType<typeof setTimeout>;

	let showManifestModal = false;
	let showValvesModal = false;
	let selectedTool = null;

	let showDeleteConfirm = false;

	let tools = [];
	let filteredItems = [];

	let tagsContainerElement: HTMLDivElement;
	let viewOption = '';

	let showImportModal = false;

	$: if (query !== undefined) {
		clearTimeout(searchDebounceTimer);
		searchDebounceTimer = setTimeout(() => {
			setFilteredItems();
		}, 300);
	}

	$: if (tools && viewOption !== undefined) {
		setFilteredItems();
	}

	const setFilteredItems = () => {
		filteredItems = tools.filter((t) => {
			if (query === '' && viewOption === '') return true;
			const lowerQuery = query.toLowerCase();
			return (
				(query === '' || (t.name || '').toLowerCase().includes(lowerQuery)) &&
				(viewOption === '' ||
					(viewOption === 'created' && t.user_id === $user?.id) ||
					(viewOption === 'shared' && t.user_id !== $user?.id))
			);
		});
	};

	const shareHandler = async (tool) => {
		const item = await getToolById(localStorage.token, tool.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		toast.success($i18n.t('Redirecting you to Open WebUI Community'));

		const url = 'https://openwebui.com';

		const tab = await window.open(`${url}/tools/create`, '_blank');

		const messageHandler = (event) => {
			if (event.origin !== url) return;
			if (event.data === 'loaded') {
				tab.postMessage(JSON.stringify(item), '*');
				window.removeEventListener('message', messageHandler);
			}
		};

		window.addEventListener('message', messageHandler, false);
		console.log(item);
	};

	const cloneHandler = async (tool) => {
		const _tool = await getToolById(localStorage.token, tool.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (_tool) {
			sessionStorage.tool = JSON.stringify({
				..._tool,
				id: `${_tool.id}_clone`,
				name: `${_tool.name} (Clone)`
			});
			goto('/workspace/tools/create');
		}
	};

	const exportHandler = async (tool) => {
		const _tool = await getToolById(localStorage.token, tool.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (_tool) {
			let blob = new Blob([JSON.stringify([_tool])], {
				type: 'application/json'
			});
			saveAs(blob, `tool-${_tool.id}-export-${Date.now()}.json`);
		}
	};

	const deleteHandler = async (tool) => {
		const res = await deleteToolById(localStorage.token, tool.id).catch((error) => {
			toast.error(`${error}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Tool deleted successfully'));
			await init();
		}
	};

	const init = async () => {
		tools = await getToolList(localStorage.token);
		_tools.set(await getTools(localStorage.token));
	};

	onMount(async () => {
		viewOption = localStorage?.workspaceViewOption || '';
		await init();
		loaded = true;

		const onKeyDown = (event) => {
			if (event.key === 'Shift') {
				shiftKey = true;
			}
		};

		const onKeyUp = (event) => {
			if (event.key === 'Shift') {
				shiftKey = false;
			}
		};

		const onBlur = () => {
			shiftKey = false;
		};

		window.addEventListener('keydown', onKeyDown);
		window.addEventListener('keyup', onKeyUp);
		window.addEventListener('blur-sm', onBlur);

		return () => {
			clearTimeout(searchDebounceTimer);
			window.removeEventListener('keydown', onKeyDown);
			window.removeEventListener('keyup', onKeyUp);
			window.removeEventListener('blur-sm', onBlur);
		};
	});

	onDestroy(() => {
		clearTimeout(searchDebounceTimer);
	});
</script>

<svelte:head>
	<title>
		{$i18n.t('Tools')} • {$WEBUI_NAME}
	</title>
</svelte:head>

<ImportModal
	bind:show={showImportModal}
	onImport={(tool) => {
		sessionStorage.tool = JSON.stringify({
			...tool
		});
		goto('/workspace/tools/create');
	}}
	loadUrlHandler={async (url) => {
		return await loadToolByUrl(localStorage.token, url);
	}}
	successMessage={$i18n.t('Tool imported successfully')}
/>

{#if loaded}
	<div class="flex flex-col h-full min-h-0 overflow-hidden">
	<div class="flex flex-col gap-2 px-1 mt-1.5 mb-4 shrink-0">
		<input
			id="documents-import-input"
			bind:this={toolsImportInputElement}
			bind:files={importFiles}
			type="file"
			accept=".json"
			hidden
			on:change={() => {
				console.log(importFiles);
				showConfirm = true;
			}}
		/>

		<div class="flex justify-between items-center">
			<div class="flex items-center gap-3 shrink-0">
				<div class="flex items-center justify-center w-9 h-9 rounded-xl bg-sky-500/10 dark:bg-sky-500/15">
					<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-5 text-sky-600 dark:text-sky-400">
						<path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z" />
					</svg>
				</div>
				<div>
					<div class="text-xl font-semibold">{$i18n.t('Tools')}</div>
					<div class="text-xs text-gray-500 dark:text-gray-400">{filteredItems.length} 项</div>
				</div>
			</div>

			<div class="flex w-full justify-end gap-1.5">
			<!-- {#if $user?.role === 'admin' || $user?.permissions?.workspace?.tools_import}
				<button
					class="flex text-xs items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-gray-200 transition border border-gray-200/50 dark:border-gray-700/50"
					on:click={() => {
						toolsImportInputElement.click();
					}}
				>
					<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-3.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
					</svg>
					<span class="font-medium">{$i18n.t('Import')}</span>
				</button>
			{/if} -->

			<!-- {#if tools.length && ($user?.role === 'admin' || $user?.permissions?.workspace?.tools_export)}
				<button
					class="flex text-xs items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-gray-200 transition border border-gray-200/50 dark:border-gray-700/50"
					on:click={async () => {
						const _tools = await exportTools(localStorage.token).catch((error) => {
							toast.error(`${error}`);
							return null;
						});

						if (_tools) {
							let blob = new Blob([JSON.stringify(_tools)], {
								type: 'application/json'
							});
							saveAs(blob, `tools-export-${Date.now()}.json`);
						}
					}}
				>
					<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-3.5">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
					</svg>
					<span class="font-medium">{$i18n.t('Export')}</span>
				</button>
			{/if} -->

				{#if $user?.role === 'admin'}
					<AddToolMenu
						createHandler={() => {
							goto('/workspace/tools/create');
						}}
						importFromLinkHandler={() => {
							showImportModal = true;
						}}
					>
						<div
							class="px-3 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition font-medium text-sm flex items-center gap-1.5 border border-gray-200/60 dark:border-gray-700/60"
						>
							<Plus className="size-3.5" strokeWidth="2.5" />
							<div class="hidden md:block text-xs">{$i18n.t('New Tool')}</div>
						</div>
					</AddToolMenu>
				{:else}
					<a
						class="px-3 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 text-gray-700 dark:bg-gray-800 dark:hover:bg-gray-700 dark:text-gray-200 transition font-medium text-sm flex items-center gap-1.5 border border-gray-200/60 dark:border-gray-700/60"
						href="/workspace/tools/create"
					>
						<Plus className="size-3.5" strokeWidth="2.5" />
						<div class="hidden md:block text-xs">{$i18n.t('New Tool')}</div>
					</a>
				{/if}
			</div>
		</div>
	</div>

	<div
		class="py-2.5 bg-white dark:bg-gray-900 rounded-2xl border border-gray-200/60 dark:border-gray-800/60 shadow-sm min-h-0 flex flex-col overflow-hidden"
		style="flex: 1 1 0; max-height: calc(100% - 7rem);"
	>
		<div class="flex w-full space-x-2 py-0.5 px-4 pb-2.5 shrink-0">
			<div class="flex flex-1 items-center bg-gray-50 dark:bg-gray-850 rounded-xl px-3 py-1.5 transition focus-within:ring-2 focus-within:ring-gray-300/50 dark:focus-within:ring-gray-600/50 focus-within:bg-white dark:focus-within:bg-gray-900">
				<Search className="size-3.5 text-gray-400 shrink-0" />
				<input
					class="w-full text-sm py-0.5 pl-2 outline-hidden bg-transparent placeholder:text-gray-400"
					bind:value={query}
					aria-label={$i18n.t('Search Tools')}
					placeholder={$i18n.t('Search Tools')}
				/>
				{#if query}
					<button
						class="p-0.5 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition ml-1"
						aria-label={$i18n.t('Clear search')}
						on:click={() => {
							query = '';
						}}
					>
						<XMark className="size-3" strokeWidth="2" />
					</button>
				{/if}
			</div>
		</div>

		<div
			class="px-3.5 flex w-full bg-transparent overflow-x-auto scrollbar-none shrink-0"
			on:wheel={(e) => {
				if (e.deltaY !== 0) {
					e.preventDefault();
					e.currentTarget.scrollLeft += e.deltaY;
				}
			}}
		>
			<div
				class="flex gap-0.5 w-fit text-center text-sm rounded-full bg-transparent px-1 whitespace-nowrap"
				bind:this={tagsContainerElement}
			>
				<ViewSelector
					bind:value={viewOption}
					onChange={async (value) => {
						localStorage.workspaceViewOption = value;
						await tick();
					}}
				/>
			</div>
		</div>

		{#if (filteredItems ?? []).length !== 0}
			<div class="flex-1 min-h-0 overflow-y-auto scrollbar-hidden mt-2 px-3">
			<div class="gap-2.5 grid lg:grid-cols-2">
				{#each filteredItems as tool}
					<div
						class="group flex text-left w-full px-4 py-3.5 transition-all duration-200 rounded-xl border border-transparent hover:border-gray-200/60 dark:hover:border-gray-700/40 hover:shadow-sm {tool.write_access
							? 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-850/60'
							: 'opacity-70'}"
					>
						<div class="flex items-start gap-3 flex-1 min-w-0">
							<div class="flex items-center justify-center w-10 h-10 rounded-lg bg-sky-50 dark:bg-sky-500/10 shrink-0 mt-0.5 group-hover:bg-sky-100 dark:group-hover:bg-sky-500/20 transition-colors">
								<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-5 text-sky-600 dark:text-sky-400">
									<path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z" />
								</svg>
							</div>
							{#if tool.write_access}
								<a
									class="flex-1 min-w-0"
									href={`/workspace/tools/edit?id=${encodeURIComponent(tool.id)}`}
								>
									<div class="flex items-center gap-2 mb-1">
										<Tooltip content={tool?.meta?.description ?? tool.name} placement="top-start">
											<div class="text-sm font-semibold line-clamp-1">
												{tool.name}
											</div>
										</Tooltip>
										{#if tool?.meta?.manifest?.version}
											<div class="text-xs text-sky-500 dark:text-sky-400 font-mono shrink-0">
												v{tool?.meta?.manifest?.version ?? ''}
											</div>
										{/if}
									</div>
									<div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
										<Tooltip
											content={tool?.user?.email ?? $i18n.t('Deleted User')}
											className="flex shrink-0"
											placement="top-start"
										>
											<span>{$i18n.t('By {{name}}', {
												name: capitalizeFirstLetter(
													tool?.user?.name ?? tool?.user?.email ?? $i18n.t('Deleted User')
												)
											})}</span>
										</Tooltip>
										{#if tool?.updated_at}
											<span class="text-gray-300 dark:text-gray-600">·</span>
											<Tooltip content={dayjs(tool.updated_at * 1000).format('LLLL')}>
												<span class="shrink-0">
													{$i18n.t('Updated')} {dayjs(tool.updated_at * 1000).fromNow()}
												</span>
											</Tooltip>
										{/if}
									</div>
								</a>
							{:else}
								<div class="flex-1 min-w-0">
									<div class="flex items-center justify-between gap-2 mb-1">
										<Tooltip content={tool?.meta?.description ?? tool.name} placement="top-start">
											<div class="flex items-center gap-2">
												<div class="text-sm font-semibold line-clamp-1">
													{tool.name}
												</div>
												{#if tool?.meta?.manifest?.version}
													<div class="text-xs text-sky-500 dark:text-sky-400 font-mono shrink-0">
														v{tool?.meta?.manifest?.version ?? ''}
													</div>
												{/if}
											</div>
										</Tooltip>
										<Badge type="muted" content={$i18n.t('Read Only')} />
									</div>
									<div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
										<Tooltip
											content={tool?.user?.email ?? $i18n.t('Deleted User')}
											className="flex shrink-0"
											placement="top-start"
										>
											<span>{$i18n.t('By {{name}}', {
												name: capitalizeFirstLetter(
													tool?.user?.name ?? tool?.user?.email ?? $i18n.t('Deleted User')
												)
											})}</span>
										</Tooltip>
										{#if tool?.updated_at}
											<span class="text-gray-300 dark:text-gray-600">·</span>
											<Tooltip content={dayjs(tool.updated_at * 1000).format('LLLL')}>
												<span class="shrink-0">
													{$i18n.t('Updated')} {dayjs(tool.updated_at * 1000).fromNow()}
												</span>
											</Tooltip>
										{/if}
									</div>
								</div>
							{/if}
						</div>
						{#if tool.write_access}
							<div class="flex flex-row gap-0.5 self-center opacity-0 group-hover:opacity-100 transition-opacity">
								{#if shiftKey}
									<Tooltip content={$i18n.t('Delete')}>
										<button
											class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
											type="button"
											aria-label={$i18n.t('Delete')}
											on:click={() => {
												deleteHandler(tool);
											}}
										>
											<GarbageBin />
										</button>
									</Tooltip>
								{:else}
									{#if tool?.meta?.manifest?.funding_url ?? false}
										<Tooltip content="Support">
											<button
												class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
												type="button"
												aria-label={$i18n.t('Support')}
												on:click={() => {
													selectedTool = tool;
													showManifestModal = true;
												}}
											>
												<Heart />
											</button>
										</Tooltip>
									{/if}

									<Tooltip content={$i18n.t('Valves')}>
										<button
											class="self-center w-fit text-sm px-2 py-2 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
											type="button"
											aria-label={$i18n.t('Valves')}
											on:click={() => {
												selectedTool = tool;
												showValvesModal = true;
											}}
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												fill="none"
												viewBox="0 0 24 24"
												stroke-width="1.5"
												stroke="currentColor"
												class="size-4"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z"
												/>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
												/>
											</svg>
										</button>
									</Tooltip>

									<ToolMenu
										editHandler={() => {
											goto(`/workspace/tools/edit?id=${encodeURIComponent(tool.id)}`);
										}}
										shareHandler={() => {
											shareHandler(tool);
										}}
										cloneHandler={() => {
											cloneHandler(tool);
										}}
										exportHandler={() => {
											exportHandler(tool);
										}}
										deleteHandler={async () => {
											selectedTool = tool;
											showDeleteConfirm = true;
										}}
										onClose={() => {}}
									>
										<button
											class="self-center w-fit text-sm p-1.5 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-xl"
											type="button"
										>
											<EllipsisHorizontal className="size-5" />
										</button>
									</ToolMenu>
								{/if}
							</div>
						{/if}
					</div>
				{/each}
			</div>
			</div>
		{:else}
			<div class="w-full flex flex-col justify-center items-center py-20 flex-1">
				<div class="max-w-sm text-center">
					<div class="flex items-center justify-center w-16 h-16 rounded-2xl bg-gray-100 dark:bg-gray-800 mx-auto mb-4">
						<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="size-8 text-gray-400">
							<path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17 17.25 21A2.652 2.652 0 0 0 21 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 1 1-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 0 0 4.486-6.336l-3.276 3.277a3.004 3.004 0 0 1-2.25-2.25l3.276-3.276a4.5 4.5 0 0 0-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437 1.745-1.437m6.615 8.206L15.75 15.75M4.867 19.125h.008v.008h-.008v-.008Z" />
						</svg>
					</div>
					<div class="text-base font-semibold mb-1.5">{$i18n.t('No tools found')}</div>
				</div>
			</div>
		{/if}
	</div>

	</div>

	<DeleteConfirmDialog
		bind:show={showDeleteConfirm}
		title={$i18n.t('Delete tool?')}
		on:confirm={() => {
			deleteHandler(selectedTool);
		}}
	>
		<div class=" text-sm text-gray-500 truncate">
			{$i18n.t('This will delete')} <span class="  font-medium">{selectedTool.name}</span>.
		</div>
	</DeleteConfirmDialog>

	<ValvesModal bind:show={showValvesModal} type="tool" id={selectedTool?.id ?? null} />
	<ManifestModal bind:show={showManifestModal} manifest={selectedTool?.meta?.manifest ?? {}} />

	<ConfirmDialog
		bind:show={showConfirm}
		on:confirm={() => {
			const reader = new FileReader();
			reader.onload = async (event) => {
				const _tools = JSON.parse(event.target.result);
				console.log(_tools);

				for (const tool of _tools) {
					const res = await createNewTool(localStorage.token, tool).catch((error) => {
						toast.error(`${error}`);
						return null;
					});
				}

				toast.success($i18n.t('Tool imported successfully'));
				await init();
				importFiles = null;
				toolsImportInputElement.value = '';
			};

			reader.readAsText(importFiles[0]);
		}}
	>
		<div class="text-sm text-gray-500">
			<div class=" bg-yellow-500/20 text-yellow-700 dark:text-yellow-200 rounded-lg px-4 py-3">
				<div>{$i18n.t('Please carefully review the following warnings:')}</div>

				<ul class=" mt-1 list-disc pl-4 text-xs">
					<li>
						{$i18n.t('Tools have a function calling system that allows arbitrary code execution.')}.
					</li>
					<li>{$i18n.t('Do not install tools from sources you do not fully trust.')}</li>
				</ul>
			</div>

			<div class="my-3">
				{$i18n.t(
					'I acknowledge that I have read and I understand the implications of my action. I am aware of the risks associated with executing arbitrary code and I have verified the trustworthiness of the source.'
				)}
			</div>
		</div>
	</ConfirmDialog>
{:else}
	<div class="w-full h-full flex justify-center items-center">
		<Spinner className="size-5" />
	</div>
{/if}
