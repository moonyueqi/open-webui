<script lang="ts">
	import { getContext, onMount } from 'svelte';

	import { getSkillItems } from '$lib/apis/skills';

	import Dropdown from '$lib/components/automations/_Dropdown.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Check from '$lib/components/icons/Check.svelte';
	import Keyframes from '$lib/components/icons/Keyframes.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext('i18n');

	export let skill_ids: string[] = [];

	export let side: 'top' | 'bottom' = 'top';
	export let align: 'start' | 'end' = 'start';

	/** Optional callback when selection changes */
	export let onChange: () => void = () => {};

	let showDropdown = false;
	let search = '';
	let loading = false;
	let items: any[] = [];
	let loaded = false;

	$: selectedCount = (skill_ids ?? []).length;

	$: filteredSkills = (() => {
		if (!search) return items;
		const q = search.toLowerCase();
		return items.filter(
			(s) =>
				(s?.name ?? '').toLowerCase().includes(q) ||
				(s?.id ?? '').toLowerCase().includes(q) ||
				(s?.description ?? '').toLowerCase().includes(q)
		);
	})();

	const ensureLoaded = async () => {
		if (loaded) return;
		loading = true;
		try {
			const res = await getSkillItems(localStorage.token, null).catch(() => null);
			items = res?.items ?? [];
		} catch {
			items = [];
		}
		loaded = true;
		loading = false;
	};

	const toggle = (id: string) => {
		const set = new Set(skill_ids ?? []);
		if (set.has(id)) {
			set.delete(id);
		} else {
			set.add(id);
		}
		skill_ids = Array.from(set);
		onChange();
	};

	onMount(() => {
		ensureLoaded();
	});

	$: if (showDropdown) {
		ensureLoaded();
	}
</script>

<Dropdown bind:show={showDropdown} {side} {align}>
	<button
		type="button"
		class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-2xl text-xs transition
			text-gray-600 dark:text-gray-400 hover:bg-black/5 dark:hover:bg-white/5"
	>
		<Keyframes className="size-3.5 shrink-0" strokeWidth="1.75" />
		<span class="whitespace-nowrap">{$i18n.t('Skills')}</span>
		{#if selectedCount > 0}
			<span class="text-[10px] font-medium opacity-70">{selectedCount}</span>
		{/if}
		<svg
			xmlns="http://www.w3.org/2000/svg"
			fill="none"
			viewBox="0 0 24 24"
			stroke-width="2"
			stroke="currentColor"
			class="size-2.5"
		>
			<path stroke-linecap="round" stroke-linejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
		</svg>
	</button>

	<div
		slot="content"
		class="rounded-2xl shadow-lg border border-gray-200 dark:border-gray-800 flex flex-col bg-white dark:bg-gray-850 w-72 p-1.5"
	>
		<div class="flex items-center gap-2 px-2 py-1.5 border-b border-gray-100 dark:border-gray-800/70 mb-1">
			<Search className="size-3.5 text-gray-400" strokeWidth="2.5" />
			<input
				bind:value={search}
				class="w-full text-xs bg-transparent outline-hidden placeholder:text-gray-400 dark:placeholder:text-gray-600"
				placeholder={$i18n.t('Search skills')}
				autocomplete="off"
				on:click={(e) => e.stopPropagation()}
			/>
		</div>

		<div class="overflow-y-auto scrollbar-thin max-h-60">
			<div class="px-1.5 pt-0.5 pb-1 flex items-center justify-between">
				<span class="text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">{$i18n.t('Skills')}</span>
				{#if selectedCount > 0}
					<button
						type="button"
						class="text-[10px] text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition normal-case"
						on:click={() => {
							skill_ids = [];
							onChange();
						}}
					>
						{$i18n.t('Clear')}
					</button>
				{/if}
			</div>

			{#if loading && filteredSkills.length === 0}
				<div class="flex justify-center py-4">
					<Spinner className="size-4" />
				</div>
			{:else}
				{#each filteredSkills as skill (skill.id)}
					{@const selected = (skill_ids ?? []).includes(skill.id)}
					<Tooltip
						content={skill?.description || skill?.name || skill.id}
						placement="right"
					>
						<button
							type="button"
							class="w-full flex items-center gap-2 px-2 py-1.5 rounded-xl text-left text-xs transition hover:bg-gray-50 dark:hover:bg-gray-800/50 {selected
								? 'bg-gray-100 dark:bg-gray-800'
								: ''}"
							on:click={() => toggle(skill.id)}
						>
							<div class="shrink-0">
								<Keyframes
									className="size-4 {selected ? 'text-violet-500' : 'text-gray-400'}"
									strokeWidth="1.75"
								/>
							</div>
							<div class="flex-1 min-w-0">
								<div
									class="text-xs truncate {selected
										? 'text-violet-600 dark:text-violet-300 font-medium'
										: 'text-gray-700 dark:text-gray-300'}"
								>
									{skill.name}
								</div>
							</div>
							{#if selected}
								<div class="shrink-0 text-violet-500">
									<Check className="size-3.5" strokeWidth="2.5" />
								</div>
							{/if}
						</button>
					</Tooltip>
				{:else}
					<div class="px-2 py-2 text-xs text-gray-500 dark:text-gray-400">
						{$i18n.t('No results found')}
					</div>
				{/each}
			{/if}
		</div>
	</div>
</Dropdown>
