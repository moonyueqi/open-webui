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
	<div class="flex flex-col gap-3">
		{#each Object.keys(valvesSpec.properties) as property, idx}
			<div
				class="rounded-xl border border-gray-150 dark:border-gray-800/80 bg-white dark:bg-gray-900 px-4 py-3.5 transition-all duration-200 hover:border-gray-200 dark:hover:border-gray-700 hover:shadow-sm"
			>
				<div class="flex w-full items-start justify-between gap-3">
					<div class="flex flex-col min-w-0 flex-1">
						<div class="flex items-center gap-1.5">
							<span
								class="text-sm font-semibold text-gray-800 dark:text-gray-100 truncate leading-tight"
							>
								{valvesSpec.properties[property].title}
							</span>

							{#if (valvesSpec?.required ?? []).includes(property)}
								<span
									class="shrink-0 text-xs font-semibold text-red-500 dark:text-red-400 leading-none"
									title={$i18n.t('Required')}
								>
									*
								</span>
							{/if}
						</div>

						{#if (valvesSpec.properties[property]?.description ?? null) !== null}
							<div
								class="mt-1 text-xs text-gray-500 dark:text-gray-400 leading-relaxed"
							>
								{valvesSpec.properties[property].description}
							</div>
						{/if}
					</div>

					<button
						class="shrink-0 inline-flex items-center px-2.5 py-1 text-xs font-medium rounded-md transition-all duration-150
							{(valves[property] ?? null) === null
								? 'bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 hover:text-gray-700 dark:hover:text-gray-200'
								: 'bg-blue-50 dark:bg-blue-500/15 text-blue-600 dark:text-blue-400 hover:bg-blue-100 dark:hover:bg-blue-500/25 ring-1 ring-inset ring-blue-100 dark:ring-blue-500/20'}"
						type="button"
						on:click={() => {
							const propertySpec = valvesSpec.properties[property] ?? {};
							const inputType = propertySpec?.input?.type ?? null;
							const isMultiCheckbox =
								inputType === 'checkbox' && propertySpec?.input?.multiple === true;

							if ((valves[property] ?? null) === null) {
								if (isMultiCheckbox) {
									const defaultArray = propertySpec?.default ?? [];
									valves[property] = Array.isArray(defaultArray) ? [...defaultArray] : [];
								} else if ((propertySpec?.type ?? null) === 'array') {
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

				{#if (valves[property] ?? null) !== null}
					<div class="mt-3">
						{#if valvesSpec.properties[property]?.input?.type === 'checkbox' && valvesSpec.properties[property]?.input?.options}
							{@const _spec = valvesSpec.properties[property]}
							{@const _multiple = _spec.input?.multiple === true}
							<div class="flex flex-col gap-1">
								{#each _spec.input.options as option}
									{@const _value =
										typeof option === 'object' && option !== null ? option.value : option}
									{@const _label =
										typeof option === 'object' && option !== null
											? (option.label ?? option.value)
											: option}
									{@const _checked = _multiple
										? Array.isArray(valves[property]) && valves[property].includes(_value)
										: valves[property] === _value}
									<label
										class="flex items-center gap-2.5 px-2.5 py-2 rounded-md text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer transition-colors"
									>
										<input
											type={_multiple ? 'checkbox' : 'radio'}
											name="valve-{property}"
											class="size-4 accent-blue-500 cursor-pointer focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
											value={_value}
											checked={_checked}
											on:change={(e) => {
												if (_multiple) {
													const current = Array.isArray(valves[property])
														? [...valves[property]]
														: [];
													if (e.currentTarget.checked) {
														if (!current.includes(_value)) current.push(_value);
													} else {
														const idx = current.indexOf(_value);
														if (idx !== -1) current.splice(idx, 1);
													}
													valves[property] = current;
												} else {
													valves[property] = _value;
												}
												dispatch('change');
											}}
											on:mouseup={(e) => {
												e.currentTarget.blur();
											}}
										/>
										<span class="select-none">{_label}</span>
									</label>
								{/each}
							</div>
						{:else if valvesSpec.properties[property]?.enum ?? null}
							<select
								class="w-full rounded-lg py-2 px-3 text-sm text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-850 outline-hidden border border-gray-200 dark:border-gray-700 focus:border-blue-400 dark:focus:border-blue-500 focus:ring-2 focus:ring-blue-400/15 transition-colors"
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
							<div
								class="flex justify-between items-center py-2 px-3 rounded-lg bg-gray-50 dark:bg-gray-850 border border-gray-200 dark:border-gray-700"
							>
								<span class="text-sm text-gray-600 dark:text-gray-300">
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
								class="w-full rounded-lg py-2 px-3 text-sm text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-850 outline-hidden border border-gray-200 dark:border-gray-700 focus:border-blue-400 dark:focus:border-blue-500 focus:ring-2 focus:ring-blue-400/15 transition-colors placeholder:text-gray-400 dark:placeholder:text-gray-500"
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
									class="w-full rounded-lg py-2 px-3 text-sm text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-850 border border-gray-200 dark:border-gray-700 focus-within:border-blue-400 dark:focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-400/15 transition-colors"
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
									class="w-full rounded-lg py-2 px-3 text-sm text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-850 outline-hidden border border-gray-200 dark:border-gray-700 focus:border-blue-400 dark:focus:border-blue-500 focus:ring-2 focus:ring-blue-400/15 transition-colors"
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
									<div
										class="relative size-9 rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 shadow-sm"
									>
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
										class="flex-1 rounded-lg py-2 px-3 text-sm text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-850 outline-hidden border border-gray-200 dark:border-gray-700 transition-colors font-mono tracking-wide"
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
								<div class="flex flex-col items-stretch gap-2">
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
											class="w-full rounded-lg py-2 px-3 text-left text-sm text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-850 outline-hidden border border-gray-200 dark:border-gray-700 focus:border-blue-400 dark:focus:border-blue-500 focus:ring-2 focus:ring-blue-400/15 transition-colors"
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
								class="w-full rounded-lg py-2 px-3 text-sm text-gray-800 dark:text-gray-200 bg-gray-50 dark:bg-gray-850 outline-hidden border border-gray-200 dark:border-gray-700 focus:border-blue-400 dark:focus:border-blue-500 focus:ring-2 focus:ring-blue-400/15 transition-colors resize-y min-h-[72px] leading-relaxed placeholder:text-gray-400 dark:placeholder:text-gray-500"
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
	<div
		class="flex flex-col items-center justify-center py-10 px-4 text-center rounded-xl border border-dashed border-gray-200 dark:border-gray-800"
	>
		<svg
			xmlns="http://www.w3.org/2000/svg"
			fill="none"
			viewBox="0 0 24 24"
			stroke-width="1.5"
			stroke="currentColor"
			class="size-8 text-gray-300 dark:text-gray-600 mb-2"
		>
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.281Z"
			/>
			<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
		</svg>
		<div class="text-sm font-medium text-gray-500 dark:text-gray-400">
			{$i18n.t('No valves')}
		</div>
	</div>
{/if}
