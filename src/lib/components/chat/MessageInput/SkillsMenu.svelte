<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { getContext } from 'svelte';
	import { flyAndScale } from '$lib/utils/transitions';

	import { getSkillItems } from '$lib/apis/skills';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Keyframes from '$lib/components/icons/Keyframes.svelte';

	const i18n = getContext('i18n');

	export let onSelect: (skill: { id: string; name: string }) => void = () => {};

	let show = false;
	let loading = false;
	let items: any[] = [];
	let loaded = false;

	$: if (show && !loaded) {
		loadData();
	}

	async function loadData() {
		loading = true;
		try {
			const res = await getSkillItems(localStorage.token, null).catch(() => null);
			items = res?.items ?? [];
			loaded = true;
		} catch {
			items = [];
		}
		loading = false;
	}

	function handleSelect(skill: any) {
		show = false;
		onSelect(skill);
	}
</script>

<Dropdown bind:show>
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
					{#if items.length === 0}
						<div class="px-3 py-4 text-center text-sm text-gray-500">
							{$i18n.t('No results found')}
						</div>
					{:else}
						{#each items as skill (skill.id)}
							<Tooltip content={skill.description || skill.name} placement="right">
								<button
									class="flex w-full items-center gap-2 px-2.5 py-1.5 text-sm cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800/50 text-left"
									type="button"
									on:click={() => handleSelect(skill)}
								>
									<div class="shrink-0">
										<Keyframes className="size-4 text-violet-500" strokeWidth="1.75" />
									</div>
									<div class="flex-1 min-w-0">
										<div class="text-xs text-gray-700 dark:text-gray-300 truncate">
											{skill.name}
										</div>
									</div>
								</button>
							</Tooltip>
						{/each}
					{/if}
				</div>
			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>
