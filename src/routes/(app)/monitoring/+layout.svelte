<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { WEBUI_NAME, showSidebar, mobile } from '$lib/stores';
	import { page } from '$app/stores';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Sidebar from '$lib/components/icons/Sidebar.svelte';

	const i18n = getContext('i18n');

	let loaded = false;

	onMount(async () => {
		loaded = true;
	});
</script>

<svelte:head>
	<title>
		{$i18n.t('Monitoring & Alerts')} • {$WEBUI_NAME}
	</title>
</svelte:head>

{#if loaded}
	<div
		class=" relative flex flex-col w-full h-full transition-width duration-200 ease-in-out max-w-full"
	>
		<nav class="px-2.5 pt-2 pb-0.5 md:rounded-t-xl backdrop-blur-xl drag-region select-none">
			<div class="flex items-center gap-2">
				{#if $mobile}
					<div class="{$showSidebar ? 'md:hidden' : ''} self-center flex flex-none items-center">
						<Tooltip
							content={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
							interactive={true}
						>
							<button
								id="sidebar-toggle-button"
								class="cursor-pointer flex rounded-lg hover:bg-gray-100 dark:hover:bg-gray-850 transition"
								aria-label={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
								on:click={() => {
									showSidebar.set(!$showSidebar);
								}}
							>
								<div class="self-center p-1.5">
									<Sidebar />
								</div>
							</button>
						</Tooltip>
					</div>
				{/if}

				<div class="flex-1 overflow-x-auto scrollbar-none">
					<div
						class="flex gap-1 w-fit text-center text-sm font-medium py-1 touch-auto pointer-events-auto"
					>
						<a
							draggable="false"
							aria-current={$page.url.pathname.includes('/monitoring/ground') ? 'page' : null}
							class="flex items-center gap-1.5 min-w-fit px-3 py-1.5 rounded-lg transition-all duration-200 select-none {$page.url.pathname.includes(
								'/monitoring/ground'
							)
								? 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
								: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-850'}"
							href="/monitoring/ground"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
								stroke-width="1.75"
								stroke="currentColor"
								class="size-4 {$page.url.pathname.includes('/monitoring/ground')
									? 'text-emerald-600 dark:text-emerald-400'
									: ''}"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M6.429 9.75 2.25 12l4.179 2.25m0-4.5 5.571 3 5.571-3m-11.142 0L2.25 7.5 12 2.25l9.75 5.25-4.179 2.25m0 0L21.75 12l-4.179 2.25m0 0 4.179 2.25L12 21.75 2.25 16.5l4.179-2.25m11.142 0-5.571 3-5.571-3"
								/>
							</svg>
							{$i18n.t('Ground Monitoring')}
						</a>

						<a
							draggable="false"
							aria-current={$page.url.pathname.includes('/monitoring/upper-air') ? 'page' : null}
							class="flex items-center gap-1.5 min-w-fit px-3 py-1.5 rounded-lg transition-all duration-200 select-none {$page.url.pathname.includes(
								'/monitoring/upper-air'
							)
								? 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
								: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-850'}"
							href="/monitoring/upper-air"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
								stroke-width="1.75"
								stroke="currentColor"
								class="size-4 {$page.url.pathname.includes('/monitoring/upper-air')
									? 'text-sky-600 dark:text-sky-400'
									: ''}"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M2.25 15a4.5 4.5 0 0 0 4.5 4.5H18a3.75 3.75 0 0 0 1.332-7.257 3 3 0 0 0-3.758-3.848 5.25 5.25 0 0 0-10.233 2.33A4.502 4.502 0 0 0 2.25 15Z"
								/>
							</svg>
							{$i18n.t('Upper-air Monitoring')}
						</a>

						<a
							draggable="false"
							aria-current={$page.url.pathname.includes('/monitoring/jjj') ? 'page' : null}
							class="flex items-center gap-1.5 min-w-fit px-3 py-1.5 rounded-lg transition-all duration-200 select-none {$page.url.pathname.includes(
								'/monitoring/jjj'
							)
								? 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 shadow-sm'
								: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-850'}"
							href="/monitoring/jjj"
						>
							<svg
								xmlns="http://www.w3.org/2000/svg"
								fill="none"
								viewBox="0 0 24 24"
								stroke-width="1.75"
								stroke="currentColor"
								class="size-4 {$page.url.pathname.includes('/monitoring/jjj')
									? 'text-rose-600 dark:text-rose-400'
									: ''}"
							>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"
								/>
								<path
									stroke-linecap="round"
									stroke-linejoin="round"
									d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z"
								/>
							</svg>
							{$i18n.t('Beijing-Tianjin-Hebei Alerts')}
						</a>
					</div>
				</div>
			</div>
		</nav>

		<div class="pb-3 px-3 md:px-[18px] flex-1 min-h-0 flex flex-col" id="monitoring-container">
			<slot />
		</div>
	</div>
{/if}
