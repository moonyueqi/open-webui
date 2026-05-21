<script lang="ts">
	import { getContext, onMount, tick } from 'svelte';
	import { models, config } from '$lib/stores';

	import { toast } from 'svelte-sonner';
	import { copyToClipboard } from '$lib/utils';

	import XMark from '$lib/components/icons/XMark.svelte';
	import Modal from '$lib/components/common/Modal.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import MapSelector from '$lib/components/common/Valves/MapSelector.svelte';

	const i18n = getContext('i18n');

	export let show = false;
	export let variables = {};

	export let onSave = (e) => {};

	let loading = false;
	let variableValues = {};

	const submitHandler = async () => {
		onSave(variableValues);
		show = false;
	};

	const init = async () => {
		loading = true;
		variableValues = {};
		for (const variable of Object.keys(variables)) {
			if (variables[variable]?.default !== undefined) {
				variableValues[variable] = variables[variable].default;
			} else {
				variableValues[variable] = '';
			}
		}
		loading = false;

		await tick();

		const firstInputElement = document.getElementById('input-variable-0');
		if (firstInputElement) {
			firstInputElement.focus();
		}
	};

	$: if (show) {
		init();
	}
</script>

<Modal bind:show size="md">
	<div>
		<!-- Header -->
		<div class="flex items-center justify-between px-5 pt-4 pb-3">
			<div class="flex items-center gap-2">
				<svg
					xmlns="http://www.w3.org/2000/svg"
					viewBox="0 0 20 20"
					fill="currentColor"
					class="size-5 text-gray-600 dark:text-gray-300"
				>
					<path
						fill-rule="evenodd"
						d="M5.5 3A2.5 2.5 0 003 5.5v9A2.5 2.5 0 005.5 17h9a2.5 2.5 0 002.5-2.5v-9A2.5 2.5 0 0014.5 3h-9zM7 7.75A.75.75 0 017.75 7h4.5a.75.75 0 010 1.5h-4.5A.75.75 0 017 7.75zm.75 3.25a.75.75 0 000 1.5h2.5a.75.75 0 000-1.5h-2.5z"
						clip-rule="evenodd"
					/>
				</svg>
				<h3 class="text-base font-semibold text-gray-800 dark:text-gray-200">
					{$i18n.t('Input Variables')}
				</h3>
			</div>
			<button
				class="rounded-md p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
				aria-label="Close"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-4'} />
			</button>
		</div>

		<div class="border-t border-gray-100 dark:border-gray-800"></div>

		<!-- Body -->
		<div class="px-5 py-4 dark:text-gray-200">
			<form
				class="flex flex-col w-full"
				on:submit|preventDefault={() => {
					submitHandler();
				}}
			>
				<div class="max-h-[60vh] overflow-y-auto scrollbar-thin pr-0.5">
					{#if !loading}
						{#if Object.keys(variables).length === 0}
							<div
								class="flex flex-col items-center justify-center py-10 text-center text-gray-400 dark:text-gray-500"
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="1.5"
									class="size-8 mb-2 opacity-70"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M9 12h6m-3-3v6m9-3a9 9 0 11-18 0 9 9 0 0118 0z"
									/>
								</svg>
								<div class="text-sm">{$i18n.t('No variables to fill in.')}</div>
							</div>
						{:else}
							<div class="flex flex-col gap-3.5">
								{#each Object.keys(variables) as variable, idx}
									{@const { type, ...variableAttributes } = variables[variable] ?? {}}

									<div class="w-full">
										<!-- Label row -->
										<div class="flex items-center justify-between mb-1.5">
											<label
												for="input-variable-{idx}"
												class="text-xs font-medium text-gray-700 dark:text-gray-300 flex items-center gap-1.5"
											>
												<span>{variable}</span>
												{#if variables[variable]?.required ?? false}
													<span
														class="inline-flex items-center text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-red-50 text-red-600 dark:bg-red-500/10 dark:text-red-400"
													>
														*{$i18n.t('required')}
													</span>
												{/if}
											</label>
										</div>

										<!-- Input field -->
										<div class="flex">
											<div class="flex-1">
												{#if variables[variable]?.type === 'select'}
													{@const options = variableAttributes?.options ?? []}
													{@const placeholder = variableAttributes?.placeholder ?? ''}

													<select
														class="w-full rounded-lg py-2 px-3 text-sm bg-white dark:bg-gray-850 text-gray-800 dark:text-gray-200 outline-hidden border border-gray-200 dark:border-gray-800 focus:border-gray-400 dark:focus:border-gray-600 transition-colors"
														bind:value={variableValues[variable]}
														id="input-variable-{idx}"
													>
														{#if placeholder}
															<option value="" disabled selected>
																{placeholder}
															</option>
														{/if}
														{#each options as option}
															<option value={option} selected={option === variableValues[variable]}>
																{option}
															</option>
														{/each}
													</select>
												{:else if variables[variable]?.type === 'checkbox'}
													<div
														class="flex items-center gap-3 rounded-lg py-2 px-3 border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850"
													>
														<div class="flex items-center gap-2">
															<input
																type="checkbox"
																bind:checked={variableValues[variable]}
																class="size-3.5 rounded cursor-pointer border border-gray-300 dark:border-gray-700 accent-gray-700 dark:accent-gray-200"
																id="input-variable-{idx}"
																{...variableAttributes}
															/>

															<label
																for="input-variable-{idx}"
																class="text-sm text-gray-700 dark:text-gray-300 cursor-pointer"
															>
																{variables[variable]?.label ?? variable}
															</label>
														</div>

														<input
															type="text"
															class="flex-1 min-w-0 py-1 text-sm dark:text-gray-300 bg-transparent outline-hidden border-l border-gray-200 dark:border-gray-800 pl-3"
															placeholder={$i18n.t('Enter value (true/false)')}
															bind:value={variableValues[variable]}
															autocomplete="off"
															required={variables[variable]?.required ?? false}
														/>
													</div>
												{:else if variables[variable]?.type === 'color'}
													<div
														class="flex items-center gap-3 rounded-lg py-1.5 px-2 border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850"
													>
														<div class="relative size-7 shrink-0">
															<input
																type="color"
																class="size-7 rounded-md cursor-pointer border border-gray-200 dark:border-gray-700 overflow-hidden"
																value={variableValues[variable]}
																id="input-variable-{idx}"
																on:input={(e) => {
																	variableValues[variable] = e.target.value.toUpperCase();
																}}
																{...variableAttributes}
															/>
														</div>

														<input
															type="text"
															class="flex-1 min-w-0 py-1 text-sm dark:text-gray-300 bg-transparent outline-hidden"
															placeholder={$i18n.t('Enter hex color (e.g. #FF0000)')}
															bind:value={variableValues[variable]}
															autocomplete="off"
															required={variables[variable]?.required ?? false}
														/>
													</div>
												{:else if variables[variable]?.type === 'date'}
													<input
														type="date"
														class="w-full rounded-lg py-2 px-3 text-sm bg-white dark:bg-gray-850 text-gray-800 dark:text-gray-200 outline-hidden border border-gray-200 dark:border-gray-800 focus:border-gray-400 dark:focus:border-gray-600 transition-colors"
														placeholder={variables[variable]?.placeholder ?? ''}
														bind:value={variableValues[variable]}
														autocomplete="off"
														id="input-variable-{idx}"
														required={variables[variable]?.required ?? false}
														{...variableAttributes}
													/>
												{:else if variables[variable]?.type === 'datetime-local'}
													<input
														type="datetime-local"
														class="w-full rounded-lg py-2 px-3 text-sm bg-white dark:bg-gray-850 text-gray-800 dark:text-gray-200 outline-hidden border border-gray-200 dark:border-gray-800 focus:border-gray-400 dark:focus:border-gray-600 transition-colors"
														placeholder={variables[variable]?.placeholder ?? ''}
														bind:value={variableValues[variable]}
														autocomplete="off"
														id="input-variable-{idx}"
														required={variables[variable]?.required ?? false}
														{...variableAttributes}
													/>
												{:else if variables[variable]?.type === 'email'}
													<input
														type="email"
														class="w-full rounded-lg py-2 px-3 text-sm bg-white dark:bg-gray-850 text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 outline-hidden border border-gray-200 dark:border-gray-800 focus:border-gray-400 dark:focus:border-gray-600 transition-colors"
														placeholder={variables[variable]?.placeholder ?? ''}
														bind:value={variableValues[variable]}
														autocomplete="off"
														id="input-variable-{idx}"
														required={variables[variable]?.required ?? false}
														{...variableAttributes}
													/>
												{:else if variables[variable]?.type === 'month'}
													<input
														type="month"
														class="w-full rounded-lg py-2 px-3 text-sm bg-white dark:bg-gray-850 text-gray-800 dark:text-gray-200 outline-hidden border border-gray-200 dark:border-gray-800 focus:border-gray-400 dark:focus:border-gray-600 transition-colors"
														placeholder={variables[variable]?.placeholder ?? ''}
														bind:value={variableValues[variable]}
														autocomplete="off"
														id="input-variable-{idx}"
														required={variables[variable]?.required ?? false}
														{...variableAttributes}
													/>
												{:else if variables[variable]?.type === 'number'}
													<input
														type="number"
														class="w-full rounded-lg py-2 px-3 text-sm bg-white dark:bg-gray-850 text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 outline-hidden border border-gray-200 dark:border-gray-800 focus:border-gray-400 dark:focus:border-gray-600 transition-colors"
														placeholder={variables[variable]?.placeholder ?? ''}
														bind:value={variableValues[variable]}
														autocomplete="off"
														id="input-variable-{idx}"
														required={variables[variable]?.required ?? false}
														{...variableAttributes}
													/>
												{:else if variables[variable]?.type === 'range'}
													<div
														class="flex items-center gap-3 rounded-lg py-2 px-3 border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850"
													>
														<input
															type="range"
															bind:value={variableValues[variable]}
															class="flex-1 accent-gray-700 dark:accent-gray-200 cursor-pointer"
															id="input-variable-{idx}"
															{...variableAttributes}
														/>

														<input
															type="text"
															class="w-14 py-1 text-sm text-right text-gray-700 dark:text-gray-300 bg-transparent outline-hidden border-l border-gray-200 dark:border-gray-800 pl-2"
															placeholder={$i18n.t('Enter value')}
															bind:value={variableValues[variable]}
															autocomplete="off"
															required={variables[variable]?.required ?? false}
														/>
													</div>
												{:else if variables[variable]?.type === 'tel'}
													<input
														type="tel"
														class="w-full rounded-lg py-2 px-3 text-sm bg-white dark:bg-gray-850 text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 outline-hidden border border-gray-200 dark:border-gray-800 focus:border-gray-400 dark:focus:border-gray-600 transition-colors"
														placeholder={variables[variable]?.placeholder ?? ''}
														bind:value={variableValues[variable]}
														autocomplete="off"
														id="input-variable-{idx}"
														required={variables[variable]?.required ?? false}
														{...variableAttributes}
													/>
												{:else if variables[variable]?.type === 'text'}
													<input
														type="text"
														class="w-full rounded-lg py-2 px-3 text-sm bg-white dark:bg-gray-850 text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 outline-hidden border border-gray-200 dark:border-gray-800 focus:border-gray-400 dark:focus:border-gray-600 transition-colors"
														placeholder={variables[variable]?.placeholder ?? ''}
														bind:value={variableValues[variable]}
														autocomplete="off"
														id="input-variable-{idx}"
														required={variables[variable]?.required ?? false}
														{...variableAttributes}
													/>
												{:else if variables[variable]?.type === 'time'}
													<input
														type="time"
														class="w-full rounded-lg py-2 px-3 text-sm bg-white dark:bg-gray-850 text-gray-800 dark:text-gray-200 outline-hidden border border-gray-200 dark:border-gray-800 focus:border-gray-400 dark:focus:border-gray-600 transition-colors"
														placeholder={variables[variable]?.placeholder ?? ''}
														bind:value={variableValues[variable]}
														autocomplete="off"
														id="input-variable-{idx}"
														required={variables[variable]?.required ?? false}
														{...variableAttributes}
													/>
												{:else if variables[variable]?.type === 'url'}
													<input
														type="url"
														class="w-full rounded-lg py-2 px-3 text-sm bg-white dark:bg-gray-850 text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 outline-hidden border border-gray-200 dark:border-gray-800 focus:border-gray-400 dark:focus:border-gray-600 transition-colors"
														placeholder={variables[variable]?.placeholder ?? ''}
														bind:value={variableValues[variable]}
														autocomplete="off"
														id="input-variable-{idx}"
														required={variables[variable]?.required ?? false}
														{...variableAttributes}
													/>
												{:else if variables[variable]?.type === 'map'}
													<!-- EXPERIMENTAL INPUT TYPE, DO NOT USE IN PRODUCTION -->
													<div
														class="flex flex-col gap-2 rounded-lg p-2 border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-850"
													>
														<MapSelector
															setViewLocation={((variableValues[variable] ?? '').includes(',') ??
															false)
																? variableValues[variable].split(',')
																: null}
															onClick={(value) => {
																variableValues[variable] = value;
															}}
														/>

														<input
															type="text"
															class="w-full py-1.5 px-2 text-sm dark:text-gray-300 bg-transparent outline-hidden border-t border-gray-200 dark:border-gray-800"
															placeholder={$i18n.t('Enter coordinates (e.g. 51.505, -0.09)')}
															bind:value={variableValues[variable]}
															autocomplete="off"
															required={variables[variable]?.required ?? false}
														/>
													</div>
												{:else}
													<textarea
														class="w-full rounded-lg py-2 px-3 text-sm bg-white dark:bg-gray-850 text-gray-800 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500 outline-hidden border border-gray-200 dark:border-gray-800 focus:border-gray-400 dark:focus:border-gray-600 transition-colors resize-y min-h-[80px]"
														placeholder={variables[variable]?.placeholder ?? ''}
														bind:value={variableValues[variable]}
														autocomplete="off"
														id="input-variable-{idx}"
														required={variables[variable]?.required ?? false}
													/>
												{/if}
											</div>
										</div>
									</div>
								{/each}
							</div>
						{/if}
					{:else}
						<div class="flex items-center justify-center py-8">
							<Spinner className="size-5" />
						</div>
					{/if}
				</div>

				<!-- Footer -->
				<div
					class="flex justify-end gap-2 pt-4 mt-4 border-t border-gray-100 dark:border-gray-800"
				>
					<button
						class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors rounded-lg"
						type="button"
						on:click={() => {
							show = false;
						}}
					>
						{$i18n.t('Cancel')}
					</button>

					<button
						class="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-black hover:bg-gray-800 text-white dark:bg-white dark:text-black dark:hover:bg-gray-200 transition-colors rounded-lg"
						type="submit"
					>
						{$i18n.t('Save')}
					</button>
				</div>
			</form>
		</div>
	</div>
</Modal>

<style>
	input::-webkit-outer-spin-button,
	input::-webkit-inner-spin-button {
		-webkit-appearance: none;
		margin: 0;
	}

	input[type='number'] {
		-moz-appearance: textfield;
	}

	input[type='color']::-webkit-color-swatch-wrapper {
		padding: 0;
	}

	input[type='color']::-webkit-color-swatch {
		border: none;
		border-radius: 0.375rem;
	}
</style>
