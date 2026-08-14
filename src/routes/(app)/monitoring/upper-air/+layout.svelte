<script lang="ts">
	import { getContext } from 'svelte';
	import { page } from '$app/stores';

	const i18n = getContext('i18n');
</script>

<div class="flex flex-col flex-1 min-h-0">
	<div class="overflow-x-auto scrollbar-none">
		<div class="flex gap-1 w-fit text-center text-xs font-medium pb-1.5 touch-auto pointer-events-auto">
			<a
				draggable="false"
				aria-current={$page.url.pathname.includes('/monitoring/upper-air/lightning-jump')
					? 'page'
					: null}
				class="flex items-center gap-1.5 min-w-fit px-2.5 py-1.5 rounded-md transition-all duration-200 select-none {$page.url.pathname.includes(
					'/monitoring/upper-air/lightning-jump'
				)
					? 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
					: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-850'}"
				href="/monitoring/upper-air/lightning-jump"
			>
				<svg
					xmlns="http://www.w3.org/2000/svg"
					fill="none"
					viewBox="0 0 24 24"
					stroke-width="1.75"
					stroke="currentColor"
					class="size-3.5 {$page.url.pathname.includes('/monitoring/upper-air/lightning-jump')
						? 'text-amber-600 dark:text-amber-400'
						: ''}"
				>
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M3.75 13.5 10.5 3l-1.5 6.75h6.75L9 21l1.5-6.75H3.75Z"
					/>
				</svg>
				{$i18n.t('Lightning Jump Warning')}
			</a>

			<!-- 后续高空监测产品分栏在此追加，例如：
			<a href="/monitoring/upper-air/<new-product>">...</a>
			-->
		</div>
	</div>

	<hr class="border-gray-100 dark:border-gray-800 mb-2.5" />

	<div class="flex-1 min-h-0 flex flex-col">
		<slot />
	</div>
</div>
