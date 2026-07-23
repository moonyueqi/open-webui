<script lang="ts">
	import { getContext } from 'svelte';

	const i18n = getContext('i18n');
</script>

<div class="flex flex-col items-center justify-center flex-1 min-h-0 text-center py-16">
	<div class="text-gray-300 dark:text-gray-600 mb-4">
		<svg
			xmlns="http://www.w3.org/2000/svg"
			fill="none"
			viewBox="0 0 24 24"
			stroke-width="1.5"
			stroke="currentColor"
			class="size-12 mx-auto"
		>
			<path
				stroke-linecap="round"
				stroke-linejoin="round"
				d="M6.429 9.75 2.25 12l4.179 2.25m0-4.5 5.571 3 5.571-3m-11.142 0L2.25 7.5 12 2.25l9.75 5.25-4.179 2.25m0 0L21.75 12l-4.179 2.25m0 0 4.179 2.25L12 21.75 2.25 16.5l4.179-2.25m11.142 0-5.571 3-5.571-3"
			/>
		</svg>
	</div>
	<div class="text-base font-medium text-gray-500 dark:text-gray-400">
		{$i18n.t('Ground Monitoring')}
	</div>
	<div class="text-sm text-gray-400 dark:text-gray-500 mt-1">
		{$i18n.t('No data available yet')}
	</div>
</div>
