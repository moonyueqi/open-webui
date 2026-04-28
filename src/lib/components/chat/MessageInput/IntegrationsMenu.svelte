<script lang="ts">
	import { DropdownMenu } from 'bits-ui';
	import { getContext, tick } from 'svelte';
	import { flyAndScale } from '$lib/utils/transitions';

	import { user } from '$lib/stores';

	import Knobs from '$lib/components/icons/Knobs.svelte';
	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import Sparkles from '$lib/components/icons/Sparkles.svelte';
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte';
	import Photo from '$lib/components/icons/Photo.svelte';

	const i18n = getContext('i18n');

	// Kept for backwards compatibility with callers; tools are now managed by ToolsMenu.
	export let selectedToolIds: string[] = [];
	export let selectedModels: string[] = [];

	export let toggleFilters: {
		id: string;
		name: string;
		description?: string;
		icon?: string;
		has_user_valves?: boolean;
	}[] = [];
	export let selectedFilterIds: string[] = [];

	export let showWebSearchButton = false;
	export let webSearchEnabled = false;
	export let showImageGenerationButton = false;
	export let imageGenerationEnabled = false;
	export let showCodeInterpreterButton = false;
	export let codeInterpreterEnabled = false;

	export let onShowValves: (e: { type: string; id: string }) => void = () => {};
	export let onClose: () => void = () => {};
	export let closeOnOutsideClick = true;

	let show = false;
</script>

<Dropdown
	bind:show
	{closeOnOutsideClick}
	on:change={(e) => {
		if (e.detail === false) {
			onClose();
		}
	}}
>
	<Tooltip content={$i18n.t('Integrations')} placement="top">
		<slot />
	</Tooltip>
	<div slot="content">
		<DropdownMenu.Content
			class="w-full max-w-70 rounded-2xl px-1 py-1 border border-gray-100 dark:border-gray-800 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-lg max-h-72 overflow-y-auto overflow-x-hidden scrollbar-thin"
			sideOffset={4}
			alignOffset={-6}
			side="bottom"
			align="start"
			transition={flyAndScale}
		>
			{#if toggleFilters && toggleFilters.length > 0}
				{#each toggleFilters.sort( (a, b) => a.name.localeCompare( b.name, undefined, { sensitivity: 'base' } ) ) as filter (filter.id)}
					<Tooltip content={filter?.description} placement="top-start">
						<button
							class="flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800/50"
							on:click={() => {
								if (selectedFilterIds.includes(filter.id)) {
									selectedFilterIds = selectedFilterIds.filter((id) => id !== filter.id);
								} else {
									selectedFilterIds = [...selectedFilterIds, filter.id];
								}
							}}
						>
							<div class="flex-1 truncate">
								<div class="flex flex-1 gap-2 items-center">
									<div class="shrink-0">
										{#if filter?.icon}
											<div class="size-4 items-center flex justify-center">
												<img
													src={filter.icon}
													class="size-3.5 {filter.icon.includes('data:image/svg')
														? 'dark:invert-[80%]'
														: ''}"
													style="fill: currentColor;"
													alt={filter.name}
												/>
											</div>
										{:else}
											<Sparkles className="size-4" strokeWidth="1.75" />
										{/if}
									</div>

									<div class="truncate">{filter?.name}</div>
								</div>
							</div>

							{#if filter?.has_user_valves && ($user?.role === 'admin' || ($user?.permissions?.chat?.valves ?? true))}
								<div class="shrink-0">
									<Tooltip content={$i18n.t('Valves')}>
										<button
											class="self-center w-fit text-sm text-gray-600 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition rounded-full"
											type="button"
											on:click={(e) => {
												e.stopPropagation();
												e.preventDefault();
												onShowValves({
													type: 'function',
													id: filter.id
												});
											}}
										>
											<Knobs />
										</button>
									</Tooltip>
								</div>
							{/if}

							<div class="shrink-0">
								<Switch
									state={selectedFilterIds.includes(filter.id)}
									on:change={async () => {
										await tick();
									}}
								/>
							</div>
						</button>
					</Tooltip>
				{/each}
			{/if}

			{#if showWebSearchButton}
				<Tooltip content={$i18n.t('Search the internet')} placement="top-start">
					<button
						class="flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800/50"
						on:click={() => {
							webSearchEnabled = !webSearchEnabled;
						}}
					>
						<div class="flex-1 truncate">
							<div class="flex flex-1 gap-2 items-center">
								<div class="shrink-0">
									<GlobeAlt />
								</div>

								<div class="truncate">{$i18n.t('Web Search')}</div>
							</div>
						</div>

						<div class="shrink-0">
							<Switch
								state={webSearchEnabled}
								on:change={async () => {
									await tick();
								}}
							/>
						</div>
					</button>
				</Tooltip>
			{/if}

			{#if showImageGenerationButton}
				<Tooltip content={$i18n.t('Generate an image')} placement="top-start">
					<button
						class="flex w-full justify-between gap-2 items-center px-3 py-1.5 text-sm cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-800/50"
						on:click={() => {
							imageGenerationEnabled = !imageGenerationEnabled;
						}}
					>
						<div class="flex-1 truncate">
							<div class="flex flex-1 gap-2 items-center">
								<div class="shrink-0">
									<Photo className="size-4" strokeWidth="1.5" />
								</div>

								<div class="truncate">{$i18n.t('Image')}</div>
							</div>
						</div>

						<div class="shrink-0">
							<Switch
								state={imageGenerationEnabled}
								on:change={async () => {
									await tick();
								}}
							/>
						</div>
					</button>
				</Tooltip>
			{/if}
		</DropdownMenu.Content>
	</div>
</Dropdown>
