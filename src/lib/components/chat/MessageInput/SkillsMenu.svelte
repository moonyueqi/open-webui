<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { getContext } from 'svelte';
	import { flyAndScale } from '$lib/utils/transitions';

	import {
		getSkillCategories,
		getSkillsByCategoryId
	} from '$lib/apis/skill-categories';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Keyframes from '$lib/components/icons/Keyframes.svelte';
	import ChevronDown from '$lib/components/icons/ChevronDown.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';

	const i18n = getContext('i18n');

	export let onSelect: (skill: { id: string; name: string }) => void = () => {};

	let show = false;
	let loading = false;

	let categories: any[] = [];

	let expandedCategoryId: string | null = null;
	let categorySkills: any[] | null = null;
	let categorySkillsLoading = false;

	$: if (show) {
		loadData();
	}

	async function loadData() {
		if (categories.length > 0) return;
		loading = true;
		try {
			const catRes = await getSkillCategories(localStorage.token).catch(() => null);
			if (catRes?.items) {
				categories = catRes.items;
			}
		} catch {
			categories = [];
		}
		loading = false;
	}

	async function toggleCategory(categoryId: string) {
		if (expandedCategoryId === categoryId) {
			expandedCategoryId = null;
			categorySkills = null;
			return;
		}

		expandedCategoryId = categoryId;
		categorySkills = null;
		categorySkillsLoading = true;

		try {
			const res = await getSkillsByCategoryId(localStorage.token, categoryId);
			if (res?.items) {
				categorySkills = res.items;
			} else {
				categorySkills = [];
			}
		} catch {
			categorySkills = [];
		}
		categorySkillsLoading = false;
	}

	function handleSelect(skill: any) {
		show = false;
		expandedCategoryId = null;
		categorySkills = null;
		onSelect(skill);
	}
</script>

<Dropdown
	bind:show
	on:change={(e) => {
		if (e.detail === false) {
			expandedCategoryId = null;
			categorySkills = null;
		}
	}}
>
	<Tooltip content={$i18n.t('Skills')} placement="top">
		<button
			type="button"
			class="flex gap-1 items-center px-2.5 h-8 text-sm rounded-full transition-colors duration-200 outline-hidden focus:outline-hidden text-gray-700 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-800"
		>
			<Keyframes className="size-4" strokeWidth="1.75" />
			<span class="text-xs font-medium whitespace-nowrap">{$i18n.t('Skills')}</span>
		</button>
	</Tooltip>

	<div slot="content">
		<DropdownMenu.Content
			class="w-56 rounded-2xl px-1 py-1 border border-gray-100 dark:border-gray-800 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-lg max-h-80 overflow-hidden"
			sideOffset={4}
			alignOffset={-6}
			side="top"
			align="start"
			transition={flyAndScale}
		>
			{#if loading}
				<div class="flex items-center justify-center py-6 text-sm text-gray-500">
					<Spinner className="size-4" />
				</div>
			{:else}
				<div class="overflow-y-auto max-h-72 py-0.5">
					{#if categories.length === 0}
						<div class="px-3 py-4 text-center text-sm text-gray-500">
							{$i18n.t('No results found')}
						</div>
					{:else}
						{#each categories as category (category.id)}
							<div
								class="px-2.5 py-1.5 rounded-xl w-full text-left flex justify-between items-center text-sm hover:bg-gray-50 dark:hover:bg-gray-800/50"
							>
								<button
									class="w-full flex-1 flex items-center gap-1.5"
									type="button"
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
										<div class="line-clamp-1 flex-1 text-sm font-medium">
											{category.name}
										</div>
									</Tooltip>
								</button>
							</div>

							{#if expandedCategoryId === category.id}
								<div class="pl-6 mb-1 flex flex-col gap-0.5">
									{#if categorySkillsLoading}
										<div class="py-1.5 flex justify-center">
											<Spinner className="size-3" />
										</div>
									{:else if categorySkills && categorySkills.length === 0}
										<div
											class="text-xs text-gray-500 dark:text-gray-400 italic py-1 px-2"
										>
											{$i18n.t('No results found')}
										</div>
									{:else if categorySkills}
										{#each categorySkills as skill (skill.id)}
											<Tooltip
												content={skill.description || skill.name}
												placement="right"
											>
												<button
													class="flex w-full items-center gap-2 px-2.5 py-1.5 text-sm cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800/50 text-left"
													type="button"
													on:click={() => handleSelect(skill)}
												>
													<div class="shrink-0">
														<Keyframes
															className="size-3.5 text-violet-500"
															strokeWidth="1.75"
														/>
													</div>
													<div class="flex-1 min-w-0">
														<div
															class="text-xs text-gray-700 dark:text-gray-300 truncate"
														>
															{skill.name}
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
			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>
