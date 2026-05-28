<script lang="ts">
	import { createEventDispatcher, getContext } from 'svelte';
	import { toast } from 'svelte-sonner';

	import Modal from '$lib/components/common/Modal.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	import { createCalendar } from '$lib/apis/calendar';

	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	export let show = false;

	let name = '';
	let color = '#3b82f6';
	let loading = false;

	const PRESET_COLORS = [
		'#3b82f6', // 蓝
		'#6366f1', // 靛蓝
		'#8b5cf6', // 紫
		'#ec4899', // 粉
		'#ef4444', // 红
		'#f97316', // 橙
		'#f59e0b', // 琥珀
		'#22c55e', // 绿
		'#10b981', // 翠绿
		'#06b6d4' // 青
	];

	function reset() {
		name = '';
		color = '#3b82f6';
		loading = false;
	}

	$: if (show) reset();

	const submitHandler = async () => {
		if (!name.trim()) {
			toast.error($i18n.t('Name is required'));
			return;
		}

		loading = true;
		try {
			const result = await createCalendar(localStorage.token, {
				name: name.trim(),
				color
			});
			if (result) {
				toast.success($i18n.t('Calendar created'));
				dispatch('created', result);
				show = false;
			}
		} catch (err) {
			toast.error(`${err}`);
		} finally {
			loading = false;
		}
	};
</script>

<Modal size="sm" bind:show>
	<div>
		<!-- Header -->
		<div class="flex items-center justify-between gap-2 dark:text-gray-100 px-5 pt-4 pb-2">
			<div class="flex items-center gap-3 flex-1 min-w-0">
				<div
					class="flex items-center justify-center w-9 h-9 rounded-xl shrink-0 shadow-sm"
					style="background-color: {color};"
				>
					<svg
						xmlns="http://www.w3.org/2000/svg"
						fill="none"
						viewBox="0 0 24 24"
						stroke-width="2"
						stroke="white"
						class="size-4"
					>
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 0 1 2.25-2.25h13.5A2.25 2.25 0 0 1 21 7.5v11.25m-18 0A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75m-18 0v-7.5A2.25 2.25 0 0 1 5.25 9h13.5A2.25 2.25 0 0 1 21 11.25v7.5"
						/>
					</svg>
				</div>
				<h3 class="text-lg font-semibold">{$i18n.t('New Calendar')}</h3>
			</div>
			<button
				class="self-center shrink-0 p-1.5 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition"
				aria-label={$i18n.t('Close')}
				on:click={() => (show = false)}
			>
				<XMark className="size-5" />
			</button>
		</div>

		<!-- 表单 -->
		<div class="px-5 pt-3 pb-4 flex flex-col gap-4">
			<!-- 名称 -->
			<div>
				<div class="mb-1.5 text-xs text-gray-500 dark:text-gray-400 font-medium">{$i18n.t('Name')}</div>
				<input
					class="w-full text-sm bg-gray-50 dark:bg-gray-850/60 hover:bg-gray-100 dark:hover:bg-gray-800 focus:bg-gray-100 dark:focus:bg-gray-800 outline-hidden font-primary px-3 py-2 rounded-xl border border-transparent focus:border-gray-300 dark:focus:border-gray-700 transition placeholder:text-gray-400 dark:placeholder:text-gray-600"
					type="text"
					bind:value={name}
					placeholder={$i18n.t('Calendar name')}
					on:keydown={(e) => {
						if (e.key === 'Enter') submitHandler();
					}}
				/>
			</div>

			<!-- 颜色 -->
			<div>
				<div class="mb-2 text-xs text-gray-500 dark:text-gray-400 font-medium">{$i18n.t('Color')}</div>
				<div class="flex items-center gap-2 flex-wrap">
					{#each PRESET_COLORS as c}
						<button
							class="size-7 rounded-full transition-all border-2 flex items-center justify-center {color ===
							c
								? 'border-gray-800 dark:border-white scale-110 shadow-md'
								: 'border-transparent hover:scale-110'}"
							style="background-color: {c};"
							on:click={() => (color = c)}
							aria-label={c}
						>
							{#if color === c}
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 24 24"
									fill="none"
									stroke="white"
									stroke-width="3"
									class="size-3.5"
								>
									<path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5" />
								</svg>
							{/if}
						</button>
					{/each}

					<label
						class="size-7 rounded-full overflow-hidden cursor-pointer border-2 transition-all relative {!PRESET_COLORS.includes(
							color
						)
							? 'border-gray-800 dark:border-white scale-110 shadow-md'
							: 'border-transparent hover:scale-110'}"
						style="background: conic-gradient(red, yellow, lime, aqua, blue, magenta, red);"
						title={$i18n.t('Custom color')}
					>
						<input type="color" bind:value={color} class="opacity-0 w-0 h-0 absolute" />
					</label>
				</div>
			</div>
		</div>

		<!-- Footer -->
		<div
			class="flex items-center justify-end px-4 pb-3.5 pt-2 gap-1.5 border-t border-gray-100 dark:border-gray-850"
		>
			<button
				class="px-3 py-2 text-xs font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-800 transition"
				type="button"
				on:click={() => (show = false)}
			>
				{$i18n.t('Cancel')}
			</button>
			<button
				class="px-3 py-2 text-xs font-medium bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-xl flex items-center gap-1.5 disabled:opacity-50 {loading
					? 'cursor-not-allowed'
					: ''}"
				on:click={submitHandler}
				type="button"
				disabled={loading}
			>
				{$i18n.t('Create')}
				{#if loading}
					<span class="shrink-0"><Spinner className="size-3" /></span>
				{/if}
			</button>
		</div>
	</div>
</Modal>
