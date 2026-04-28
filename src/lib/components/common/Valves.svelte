<script>
	import { onMount, getContext, createEventDispatcher } from 'svelte';
	const dispatch = createEventDispatcher();
	const i18n = getContext('i18n');

	import Switch from './Switch.svelte';
	import SensitiveInput from './SensitiveInput.svelte';
	import MapSelector from './Valves/MapSelector.svelte';

	export let valvesSpec = null;
	export let valves = {};
</script>

{#if valvesSpec && Object.keys(valvesSpec?.properties ?? {}).length}
	<div class="flex flex-col gap-2.5">
		{#each Object.keys(valvesSpec.properties) as property, idx}
			<div class="rounded-lg border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900 p-3 transition-all hover:border-gray-200 dark:hover:border-gray-700">
				<div class="flex w-full items-center justify-between gap-2">
					<div class="flex items-center gap-1.5 min-w-0">
						<span class="text-xs font-semibold text-gray-700 dark:text-gray-200 truncate">
							{valvesSpec.properties[property].title}
						</span>

						{#if (valvesSpec?.required ?? []).includes(property)}
							<span class="shrink-0 text-[10px] font-medium text-red-400 dark:text-red-400">*</span>
						{/if}
					</div>

					<button
						class="shrink-0 px-2.5 py-1 text-[11px] font-medium rounded-md transition-all
							{(valves[property] ?? null) === null
								? 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
								: 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-900/50'}"
						type="button"
						on:click={() => {
							const propertySpec = valvesSpec.properties[property] ?? {};

							if ((valves[property] ?? null) === null) {
								if ((propertySpec?.type ?? null) === 'array') {
									const defaultArray = propertySpec?.default ?? [];
									valves[property] = Array.isArray(defaultArray) ? defaultArray.join(', ') : '';
								} else {
									valves[property] = propertySpec?.default ?? '';
								}
							} else {
								valves[property] = null;
							}

							dispatch('change');
						}}
					>
						{#if (valves[property] ?? null) === null}
							{#if (valvesSpec?.required ?? []).includes(property)}
								{$i18n.t('None')}
							{:else}
								{$i18n.t('Default')}
							{/if}
						{:else}
							{$i18n.t('Custom')}
						{/if}
					</button>
				</div>

				{#if (valvesSpec.properties[property]?.description ?? null) !== null}
					<div class="mt-1 text-[11px] text-gray-400 dark:text-gray-500 leading-relaxed">
						{valvesSpec.properties[property].description}
					</div>
				{/if}

				{#if (valves[property] ?? null) !== null}
					<div class="mt-2.5">
						{#if valvesSpec.properties[property]?.enum ?? null}
							<select
								class="w-full rounded-md py-2 px-3 text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-850 outline-hidden border border-gray-200 dark:border-gray-700 focus:border-blue-400 dark:focus:border-blue-500 focus:ring-1 focus:ring-blue-400/20 transition-colors"
								bind:value={valves[property]}
								on:change={() => {
									dispatch('change');
								}}
							>
								{#each valvesSpec.properties[property].enum as option}
									<option value={option} selected={option === valves[property]}>
										{option}
									</option>
								{/each}
							</select>
						{:else if (valvesSpec.properties[property]?.type ?? null) === 'boolean'}
							<div class="flex justify-between items-center py-0.5">
								<span class="text-xs text-gray-500 dark:text-gray-400">
									{valves[property] ? $i18n.t('Enabled') : $i18n.t('Disabled')}
								</span>

								<Switch
									bind:state={valves[property]}
									on:change={() => {
										dispatch('change');
									}}
								/>
							</div>
						{:else if (valvesSpec.properties[property]?.type ?? null) !== 'string'}
							<input
								class="w-full rounded-md py-2 px-3 text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-850 outline-hidden border border-gray-200 dark:border-gray-700 focus:border-blue-400 dark:focus:border-blue-500 focus:ring-1 focus:ring-blue-400/20 transition-colors"
								type="text"
								placeholder={valvesSpec.properties[property].title}
								bind:value={valves[property]}
								autocomplete="off"
								required
								on:change={() => {
									dispatch('change');
								}}
							/>
						{:else if valvesSpec.properties[property]?.input ?? null}
							{#if valvesSpec.properties[property]?.input?.type === 'password'}
								<div
									class="w-full rounded-md py-2 px-3 text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-850 border border-gray-200 dark:border-gray-700 focus-within:border-blue-400 dark:focus-within:border-blue-500 focus-within:ring-1 focus-within:ring-blue-400/20 transition-colors"
								>
									<SensitiveInput
										id="valve-{property}"
										placeholder={valvesSpec.properties[property]?.description ?? ''}
										bind:value={valves[property]}
										required={(valvesSpec?.required ?? []).includes(property)}
										on:change={() => {
											dispatch('change');
										}}
									/>
								</div>
							{:else if valvesSpec.properties[property]?.input?.type === 'select' && valvesSpec.properties[property]?.input?.options}
								<select
									class="w-full rounded-md py-2 px-3 text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-850 outline-hidden border border-gray-200 dark:border-gray-700 focus:border-blue-400 dark:focus:border-blue-500 focus:ring-1 focus:ring-blue-400/20 transition-colors"
									bind:value={valves[property]}
									on:change={() => {
										dispatch('change');
									}}
								>
									<option value="" disabled
										>{valvesSpec.properties[property]?.description ??
											$i18n.t('Select an option')}</option
									>
									{#each valvesSpec.properties[property].input.options as option}
										{#if typeof option === 'object' && option !== null}
											<option value={option.value} selected={option.value === valves[property]}>
												{option.label ?? option.value}
											</option>
										{:else}
											<option value={option} selected={option === valves[property]}>
												{option}
											</option>
										{/if}
									{/each}
								</select>
							{:else if valvesSpec.properties[property]?.input?.type === 'color'}
								<div class="flex items-center gap-2">
									<div class="relative size-8 rounded-md overflow-hidden border border-gray-200 dark:border-gray-700">
										<input
											type="color"
											class="absolute inset-0 size-full cursor-pointer opacity-0"
											value={valves[property] ?? '#000000'}
											on:input={(e) => {
												valves[property] = e.target.value.toUpperCase();
												dispatch('change');
											}}
										/>
										<div
											class="size-full"
											style="background-color: {valves[property] ?? '#000000'}"
										></div>
									</div>

									<input
										type="text"
										class="flex-1 rounded-md py-2 px-3 text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-850 outline-hidden border border-gray-200 dark:border-gray-700 transition-colors"
										placeholder={$i18n.t('Enter hex color (e.g. #FF0000)')}
										bind:value={valves[property]}
										autocomplete="off"
										disabled
										on:change={() => {
											dispatch('change');
										}}
									/>
								</div>
							{:else if valvesSpec.properties[property]?.input?.type === 'map'}
								<!-- EXPERIMENTAL INPUT TYPE, DO NOT USE IN PRODUCTION -->
								<div class="flex flex-col items-center gap-1.5">
									<MapSelector
										setViewLocation={((valves[property] ?? '').includes(',') ?? false)
											? valves[property].split(',')
											: null}
										onClick={(value) => {
											valves[property] = value;
											dispatch('change');
										}}
									/>

									{#if valves[property]}
										<input
											type="text"
											class="w-full rounded-md py-1.5 px-3 text-left text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-850 outline-hidden border border-gray-200 dark:border-gray-700 focus:border-blue-400 dark:focus:border-blue-500 focus:ring-1 focus:ring-blue-400/20 transition-colors"
											placeholder={$i18n.t('Enter coordinates (e.g. 51.505, -0.09)')}
											bind:value={valves[property]}
											autocomplete="off"
											on:change={() => {
												dispatch('change');
											}}
										/>
									{/if}
								</div>
							{/if}
						{:else}
							<textarea
								class="w-full rounded-md py-2 px-3 text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-850 outline-hidden border border-gray-200 dark:border-gray-700 focus:border-blue-400 dark:focus:border-blue-500 focus:ring-1 focus:ring-blue-400/20 transition-colors resize-y min-h-[60px]"
								placeholder={valvesSpec.properties[property].title}
								bind:value={valves[property]}
								autocomplete="off"
								required
								on:change={() => {
									dispatch('change');
								}}
							></textarea>
						{/if}
					</div>
				{/if}
			</div>
		{/each}
	</div>
{:else}
	<div class="text-center py-6 text-xs text-gray-400 dark:text-gray-500">{$i18n.t('No valves')}</div>
{/if}
