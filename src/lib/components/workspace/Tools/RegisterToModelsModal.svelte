<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher, getContext, tick } from 'svelte';

	import { models as modelsStore } from '$lib/stores';
	import { getModels } from '$lib/apis';
	import { registerToolToModels, unregisterToolFromModels } from '$lib/apis/models';

	import Modal from '$lib/components/common/Modal.svelte';
	import Checkbox from '$lib/components/common/Checkbox.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let show = false;
	export let tool: any = null;

	let loading = false;
	let saving = false;
	let query = '';

	// model id -> whether the tool is (to be) registered on it
	let selected: Record<string, boolean> = {};
	// snapshot of the state when the modal opened, to diff on save
	let initial: Record<string, boolean> = {};

	$: candidateModels = ($modelsStore ?? []).filter(
		(m: any) => m?.id && m.id !== 'arena' && !String(m.id).startsWith('arena')
	);

	$: filteredModels = candidateModels.filter((m: any) => {
		const q = query.trim().toLowerCase();
		if (!q) return true;
		return (
			String(m?.name ?? '')
				.toLowerCase()
				.includes(q) || String(m?.id ?? '').toLowerCase().includes(q)
		);
	});

	$: selectedCount = Object.values(selected).filter(Boolean).length;

	const init = () => {
		if (!tool?.id) return;
		const map: Record<string, boolean> = {};
		for (const m of candidateModels) {
			const toolIds: string[] = m?.info?.meta?.toolIds ?? [];
			map[m.id] = toolIds.includes(tool.id);
		}
		selected = map;
		initial = { ...map };
	};

	$: if (show && tool?.id) {
		init();
	}

	const saveHandler = async () => {
		if (!tool?.id) return;
		saving = true;

		const toAdd: string[] = [];
		const toRemove: string[] = [];

		for (const id of Object.keys(selected)) {
			const before = !!initial[id];
			const after = !!selected[id];
			if (after && !before) toAdd.push(id);
			if (!after && before) toRemove.push(id);
		}

		if (toAdd.length === 0 && toRemove.length === 0) {
			saving = false;
			show = false;
			return;
		}

		try {
			if (toAdd.length > 0) {
				await registerToolToModels(localStorage.token, tool.id, toAdd);
			}
			if (toRemove.length > 0) {
				await unregisterToolFromModels(localStorage.token, tool.id, toRemove);
			}

			// Refresh the models store so meta.toolIds reflects the change
			await modelsStore.set(await getModels(localStorage.token));

			toast.success($i18n.t('Saved'));
			dispatch('save');
			show = false;
		} catch (error) {
			toast.error(`${error}`);
		} finally {
			saving = false;
		}
	};
</script>

<Modal size="sm" bind:show>
	<div class="flex flex-col max-h-[80vh]">
		<div class="flex justify-between items-center px-5 pt-4 pb-1">
			<div class="text-lg font-medium">
				{$i18n.t('Register to Models')}
			</div>
			<button
				class="self-center p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition"
				aria-label={$i18n.t('Close')}
				on:click={() => (show = false)}
			>
				<XMark className="size-4" />
			</button>
		</div>

		<div class="px-5 pb-1">
			<div class="text-xs text-gray-500 dark:text-gray-400">
				{$i18n.t(
					'Selected models will automatically use "{{name}}" without manual selection in chat.',
					{ name: tool?.name ?? tool?.id ?? '' }
				)}
			</div>
		</div>

		<div class="px-5 py-2 shrink-0">
			<div
				class="flex items-center bg-gray-50 dark:bg-gray-850 rounded-xl px-3 py-1.5 transition focus-within:ring-2 focus-within:ring-gray-300/50 dark:focus-within:ring-gray-600/50"
			>
				<Search className="size-3.5 text-gray-400 shrink-0" />
				<input
					class="w-full text-sm py-0.5 pl-2 outline-hidden bg-transparent placeholder:text-gray-400"
					bind:value={query}
					placeholder={$i18n.t('Search Models')}
				/>
				{#if query}
					<button
						class="p-0.5 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition ml-1"
						aria-label={$i18n.t('Clear search')}
						on:click={() => (query = '')}
					>
						<XMark className="size-3" strokeWidth="2" />
					</button>
				{/if}
			</div>
		</div>

		<div class="px-3 pb-1 flex-1 min-h-0 overflow-y-auto scrollbar-hidden">
			{#if loading}
				<div class="w-full flex justify-center items-center py-10">
					<Spinner className="size-5" />
				</div>
			{:else if filteredModels.length === 0}
				<div class="w-full text-center text-sm text-gray-500 py-10">
					{$i18n.t('No results found')}
				</div>
			{:else}
				{#each filteredModels as model (model.id)}
					<button
						class="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-xl hover:bg-gray-50 dark:hover:bg-gray-850/60 transition text-left"
						on:click={() => {
							selected = { ...selected, [model.id]: !selected[model.id] };
						}}
					>
						<Checkbox state={selected[model.id] ? 'checked' : 'unchecked'} />
						<div class="flex-1 min-w-0">
							<div class="text-sm font-medium line-clamp-1">{model.name ?? model.id}</div>
							<div class="text-xs text-gray-400 dark:text-gray-500 line-clamp-1">{model.id}</div>
						</div>
					</button>
				{/each}
			{/if}
		</div>

		<div class="flex justify-between items-center px-5 py-3 border-t border-gray-100 dark:border-gray-850">
			<div class="text-xs text-gray-500 dark:text-gray-400">
				{$i18n.t('{{count}} selected', { count: selectedCount })}
			</div>
			<div class="flex gap-2">
				<button
					class="px-3.5 py-1.5 text-sm rounded-xl bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 transition"
					on:click={() => (show = false)}
					disabled={saving}
				>
					{$i18n.t('Cancel')}
				</button>
				<button
					class="px-3.5 py-1.5 text-sm rounded-xl bg-black hover:bg-gray-900 text-white dark:bg-white dark:hover:bg-gray-100 dark:text-black transition flex items-center gap-1.5 disabled:opacity-50"
					on:click={saveHandler}
					disabled={saving}
				>
					{#if saving}
						<Spinner className="size-3.5" />
					{/if}
					{$i18n.t('Save')}
				</button>
			</div>
		</div>
	</div>
</Modal>
