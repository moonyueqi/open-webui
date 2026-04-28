<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { createEventDispatcher } from 'svelte';
	import { onMount, getContext } from 'svelte';
	import { addUser } from '$lib/apis/auths';

	import Modal from '../../common/Modal.svelte';
	import {
		getFunctionValvesById,
		getFunctionValvesSpecById,
		updateFunctionValvesById
	} from '$lib/apis/functions';
	import { getToolValvesById, getToolValvesSpecById, updateToolValvesById } from '$lib/apis/tools';

	import {
		getUserValvesSpecById as getToolUserValvesSpecById,
		getUserValvesById as getToolUserValvesById,
		updateUserValvesById as updateToolUserValvesById,
		getTools
	} from '$lib/apis/tools';
	import {
		getUserValvesSpecById as getFunctionUserValvesSpecById,
		getUserValvesById as getFunctionUserValvesById,
		updateUserValvesById as updateFunctionUserValvesById,
		getFunctions
	} from '$lib/apis/functions';

	import Spinner from '../../common/Spinner.svelte';
	import Switch from '$lib/components/common/Switch.svelte';
	import Valves from '$lib/components/common/Valves.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let show = false;

	export let type = 'tool';
	export let id = null;
	export let userValves = false;

	let saving = false;
	let loading = false;

	let valvesSpec = null;
	let valves = {};

	const submitHandler = async () => {
		saving = true;

		if (valvesSpec) {
			// Convert string to array
			for (const property in valvesSpec.properties) {
				if (valvesSpec.properties[property]?.type === 'array') {
					if (typeof valves[property] === 'string') {
						valves[property] = (valves[property] ?? '')
							.split(',')
							.map((v) => v.trim())
							.filter((v) => v.length > 0);
					} else if (valves[property] == null) {
						valves[property] = null;
					}
				}
			}

			let res = null;

			if (userValves) {
				if (type === 'tool') {
					res = await updateToolUserValvesById(localStorage.token, id, valves).catch((error) => {
						toast.error(`${error}`);
					});
				} else if (type === 'function') {
					res = await updateFunctionUserValvesById(localStorage.token, id, valves).catch(
						(error) => {
							toast.error(`${error}`);
						}
					);
				}
			} else {
				if (type === 'tool') {
					res = await updateToolValvesById(localStorage.token, id, valves).catch((error) => {
						toast.error(`${error}`);
					});
				} else if (type === 'function') {
					res = await updateFunctionValvesById(localStorage.token, id, valves).catch((error) => {
						toast.error(`${error}`);
					});
				}
			}

			if (res) {
				toast.success($i18n.t('Valves updated successfully'));
				dispatch('save');
			}
		}

		saving = false;
	};

	const initHandler = async () => {
		loading = true;
		valves = {};
		valvesSpec = null;

		try {
			if (userValves) {
				if (type === 'tool') {
					valves = await getToolUserValvesById(localStorage.token, id);
					valvesSpec = await getToolUserValvesSpecById(localStorage.token, id);
				} else if (type === 'function') {
					valves = await getFunctionUserValvesById(localStorage.token, id);
					valvesSpec = await getFunctionUserValvesSpecById(localStorage.token, id);
				}
			} else {
				if (type === 'tool') {
					valves = await getToolValvesById(localStorage.token, id);
					valvesSpec = await getToolValvesSpecById(localStorage.token, id);
				} else if (type === 'function') {
					valves = await getFunctionValvesById(localStorage.token, id);
					valvesSpec = await getFunctionValvesSpecById(localStorage.token, id);
				}
			}

			if (!valves) {
				valves = {};
			}

			if (valvesSpec) {
				for (const property in valvesSpec.properties) {
					if (valvesSpec.properties[property]?.type === 'array') {
						if (valves[property] != null) {
							valves[property] = (Array.isArray(valves[property]) ? valves[property] : []).join(
								','
							);
						} else {
							valves[property] = null;
						}
					}
				}
			}

			loading = false;
		} catch (e) {
			toast.error(`Error fetching valves`);
			show = false;
		}
	};

	$: if (show) {
		initHandler();
	}
</script>

<Modal size="sm" bind:show>
	<div>
		<div class="flex items-center justify-between px-5 pt-4 pb-3">
			<div class="flex items-center gap-2">
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="size-5 text-gray-600 dark:text-gray-300">
					<path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd" />
				</svg>
				<h3 class="text-base font-semibold text-gray-800 dark:text-gray-200">{$i18n.t('Valves')}</h3>
			</div>
			<button
				class="rounded-md p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
				on:click={() => {
					show = false;
				}}
			>
				<XMark className={'size-4'} />
			</button>
		</div>

		<div class="border-t border-gray-100 dark:border-gray-800"></div>

		<div class="px-5 py-4 dark:text-gray-200">
			<form
				class="flex flex-col w-full"
				on:submit|preventDefault={() => {
					submitHandler();
				}}
			>
				<div class="max-h-[60vh] overflow-y-auto scrollbar-thin pr-0.5">
					{#if !loading}
						<Valves {valvesSpec} bind:valves />
					{:else}
						<div class="flex items-center justify-center py-8">
							<Spinner className="size-5" />
						</div>
					{/if}
				</div>

				<div class="flex justify-end pt-4 mt-1 border-t border-gray-100 dark:border-gray-800">
					<button
						class="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-black hover:bg-gray-800 text-white dark:bg-white dark:text-black dark:hover:bg-gray-200 transition-colors rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
						type="submit"
						disabled={saving}
					>
						{#if saving}
							<Spinner className="size-3.5" />
						{/if}
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
		/* display: none; <- Crashes Chrome on hover */
		-webkit-appearance: none;
		margin: 0; /* <-- Apparently some margin are still there even though it's hidden */
	}

	.tabs::-webkit-scrollbar {
		display: none; /* for Chrome, Safari and Opera */
	}

	.tabs {
		-ms-overflow-style: none; /* IE and Edge */
		scrollbar-width: none; /* Firefox */
	}

	input[type='number'] {
		-moz-appearance: textfield; /* Firefox */
	}
</style>
