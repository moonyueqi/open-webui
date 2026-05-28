<script lang="ts">
	import { getContext } from 'svelte';

	import { getPromptCategories, getPromptsByCategoryId } from '$lib/apis/prompt-categories';

	import Dropdown from '$lib/components/automations/_Dropdown.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import ChatBubbleOval from '$lib/components/icons/ChatBubbleOval.svelte';

	const i18n = getContext('i18n');

	/** Called when the user picks a prompt; receives the prompt content. */
	export let onSelect: (content: string) => void = () => {};

	export let side: 'top' | 'bottom' = 'top';
	export let align: 'start' | 'end' = 'start';

	let showDropdown = false;
	let search = '';

	let loading = false;
	let categories: any[] = [];
	let loaded = false;

	let expandedCategoryId: string | null = null;
	let categoryPrompts: any[] | null = null;
	let categoryPromptsLoading = false;

	$: filteredCategories = (() => {
		if (!search) return categories;
		const q = search.toLowerCase();
		return categories.filter(
			(c) =>
				(c?.name ?? '').toLowerCase().includes(q) ||
				(c?.description ?? '').toLowerCase().includes(q)
		);
	})();

	$: filteredPrompts = (() => {
		if (!categoryPrompts) return categoryPrompts;
		if (!search) return categoryPrompts;
		const q = search.toLowerCase();
		return categoryPrompts.filter(
			(p) =>
				(p?.name ?? '').toLowerCase().includes(q) ||
				(p?.content ?? '').toLowerCase().includes(q) ||
				(p?.command ?? '').toLowerCase().includes(q)
		);
	})();

	const ensureLoaded = async () => {
		if (loaded) return;
		loading = true;
		try {
			const res = await getPromptCategories(localStorage.token).catch(() => null);
			categories = res?.items ?? [];
		} catch {
			categories = [];
		}
		loaded = true;
		loading = false;
	};

	const toggleCategory = async (categoryId: string) => {
		if (expandedCategoryId === categoryId) {
			expandedCategoryId = null;
			categoryPrompts = null;
			return;
		}

		expandedCategoryId = categoryId;
		categoryPrompts = null;
		categoryPromptsLoading = true;

		try {
			const res = await getPromptsByCategoryId(localStorage.token, categoryId);
			categoryPrompts = res?.items ?? [];
		} catch {
			categoryPrompts = [];
		}
		categoryPromptsLoading = false;
	};

	const handleSelect = (content: string) => {
		showDropdown = false;
		expandedCategoryId = null;
		categoryPrompts = null;
		search = '';
		onSelect(content);
	};

	$: if (showDropdown) {
		ensureLoaded();
	}
</script>

<Dropdown
	bind:show={showDropdown}
	{side}
	{align}
	onOpenChange={(state) => {
		if (!state) {
			expandedCategoryId = null;
			categoryPrompts = null;
		}
	}}
>
	<button
		type="button"
		class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-2xl text-xs transition
			text-gray-600 dark:text-gray-400 hover:bg-black/5 dark:hover:bg-white/5"
	>
		<ChatBubbleOval className="size-3.5 shrink-0" strokeWidth="1.75" />
		<span class="whitespace-nowrap">{$i18n.t('Prompts')}</span>
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
				placeholder={$i18n.t('Search prompts')}
				autocomplete="off"
				on:click={(e) => e.stopPropagation()}
			/>
		</div>

		<div class="overflow-y-auto scrollbar-thin max-h-60">
			<div class="px-1.5 pt-0.5 pb-1 text-[11px] font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
				{$i18n.t('Prompts')}
			</div>

			{#if loading}
				<div class="flex justify-center py-4">
					<Spinner className="size-4" />
				</div>
			{:else if filteredCategories.length === 0}
				<div class="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
					{$i18n.t('No prompts found')}
				</div>
			{:else}
				{#each filteredCategories as category (category.id)}
					<button
						type="button"
						class="w-full flex items-center gap-1.5 px-2 py-1.5 rounded-xl text-left text-xs hover:bg-gray-50 dark:hover:bg-gray-800/50 transition"
						on:click={() => toggleCategory(category.id)}
					>
						<div class="shrink-0">
							{#if expandedCategoryId === category.id}
								<ChevronDown className="size-3 text-gray-400" />
							{:else}
								<ChevronRight className="size-3 text-gray-400" />
							{/if}
						</div>

						<svg
							xmlns="http://www.w3.org/2000/svg"
							fill="none"
							viewBox="0 0 24 24"
							stroke-width="1.5"
							stroke="currentColor"
							class="size-4 text-violet-500 shrink-0"
						>
							<path
								stroke-linecap="round"
								stroke-linejoin="round"
								d="M2.25 12.75V12A2.25 2.25 0 0 1 4.5 9.75h15A2.25 2.25 0 0 1 21.75 12v.75m-8.69-6.44-2.12-2.12a1.5 1.5 0 0 0-1.061-.44H4.5A2.25 2.25 0 0 0 2.25 6v12a2.25 2.25 0 0 0 2.25 2.25h15A2.25 2.25 0 0 0 21.75 18V9a2.25 2.25 0 0 0-2.25-2.25h-5.379a1.5 1.5 0 0 1-1.06-.44Z"
							/>
						</svg>

						<Tooltip
							content={category.description || category.name}
							placement="top-start"
							className="flex flex-1 min-w-0"
						>
							<div class="line-clamp-1 flex-1 text-xs font-medium text-gray-700 dark:text-gray-300">
								{category.name}
							</div>
						</Tooltip>
					</button>

					{#if expandedCategoryId === category.id}
						<div class="pl-6 mb-1 flex flex-col gap-0.5">
							{#if categoryPromptsLoading}
								<div class="py-1.5 flex justify-center">
									<Spinner className="size-3" />
								</div>
							{:else if filteredPrompts && filteredPrompts.length === 0}
								<div class="text-xs text-gray-500 dark:text-gray-400 italic py-1 px-2">
									{$i18n.t('No prompts in this category')}
								</div>
							{:else if filteredPrompts}
								{#each filteredPrompts as promptItem (promptItem.id)}
									<Tooltip content={promptItem.content || ''} placement="right">
										<button
											type="button"
											class="w-full flex items-center gap-2 px-2 py-1.5 rounded-xl text-left text-xs hover:bg-gray-50 dark:hover:bg-gray-800/50 transition"
											on:click={() => handleSelect(promptItem.content)}
										>
											<svg
												xmlns="http://www.w3.org/2000/svg"
												fill="none"
												viewBox="0 0 24 24"
												stroke-width="1.5"
												stroke="currentColor"
												class="size-3.5 text-gray-400 shrink-0"
											>
												<path
													stroke-linecap="round"
													stroke-linejoin="round"
													d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 0 1 .865-.501 48.172 48.172 0 0 0 3.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0 0 12 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018Z"
												/>
											</svg>
											<div class="flex-1 min-w-0">
												<div class="text-xs text-gray-700 dark:text-gray-300 truncate">
													{promptItem.name || promptItem.content}
												</div>
											</div>
										</button>
									</Tooltip>
								{/each}
							{/if}
						</div>
					{/if}
				{/each}
			{/if}
		</div>
	</div>
</Dropdown>
