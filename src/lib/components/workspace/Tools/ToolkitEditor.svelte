<script>
	import { toast } from 'svelte-sonner';
	import { getContext, onMount, tick } from 'svelte';

	const i18n = getContext('i18n');

	import { goto } from '$app/navigation';
	import { user } from '$lib/stores';

	import CodeEditor from '$lib/components/common/CodeEditor.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	let formElement = null;
	let loading = false;

	let showConfirm = false;

	export let edit = false;
	export let clone = false;

	export let onSave = () => {};

	export let id = '';
	export let name = '';
	export let meta = {
		description: ''
	};
	export let content = '';
	export let ownerId = '';
	export let categoryId = null;
	export let backHref = '/workspace/tools';

	let _content = '';

	$: if (content) {
		updateContent();
	}

	const updateContent = () => {
		_content = content;
	};

	$: if (name && !edit && !clone) {
		id = name.replace(/\s+/g, '_').toLowerCase();
	}

	let codeEditor;
	let boilerplate = `import os
import requests
from datetime import datetime
from pydantic import BaseModel, Field

class Tools:
    def __init__(self):
        pass

    # Add your custom tools using pure Python code here, make sure to add type hints and descriptions
	
    def get_user_name_and_email_and_id(self, __user__: dict = {}) -> str:
        """
        Get the user name, Email and ID from the user object.
        """

        # Do not include a descrption for __user__ as it should not be shown in the tool's specification
        # The session user object will be passed as a parameter when the function is called

        print(__user__)
        result = ""

        if "name" in __user__:
            result += f"User: {__user__['name']}"
        if "id" in __user__:
            result += f" (ID: {__user__['id']})"
        if "email" in __user__:
            result += f" (Email: {__user__['email']})"

        if result == "":
            result = "User: Unknown"

        return result

    def get_current_time(self) -> str:
        """
        Get the current time in a more human-readable format.
        """

        now = datetime.now()
        current_time = now.strftime("%I:%M:%S %p")  # Using 12-hour format with AM/PM
        current_date = now.strftime(
            "%A, %B %d, %Y"
        )  # Full weekday, month name, day, and year

        return f"Current Date and Time = {current_date}, {current_time}"

    def calculator(
        self,
        equation: str = Field(
            ..., description="The mathematical equation to calculate."
        ),
    ) -> str:
        """
        Calculate the result of an equation.
        """

        # Avoid using eval in production code
        # https://nedbatchelder.com/blog/201206/eval_really_is_dangerous.html
        try:
            result = eval(equation)
            return f"{equation} = {result}"
        except Exception as e:
            print(e)
            return "Invalid equation"

    def get_current_weather(
        self,
        city: str = Field(
            "New York, NY", description="Get the current weather for a given city."
        ),
    ) -> str:
        """
        Get the current weather for a given city.
        """

        api_key = os.getenv("OPENWEATHER_API_KEY")
        if not api_key:
            return (
                "API key is not set in the environment variable 'OPENWEATHER_API_KEY'."
            )

        base_url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": city,
            "appid": api_key,
            "units": "metric",  # Optional: Use 'imperial' for Fahrenheit
        }

        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx and 5xx)
            data = response.json()

            if data.get("cod") != 200:
                return f"Error fetching weather data: {data.get('message')}"

            weather_description = data["weather"][0]["description"]
            temperature = data["main"]["temp"]
            humidity = data["main"]["humidity"]
            wind_speed = data["wind"]["speed"]

            return f"Weather in {city}: {temperature}°C"
        except requests.RequestException as e:
            return f"Error fetching weather data: {str(e)}"
`;

	const saveHandler = async () => {
		loading = true;
		try {
			await onSave({
				id,
				name,
				meta,
				content,
				category_id: categoryId
			});
		} finally {
			loading = false;
		}
	};

	const submitHandler = async () => {
		if (codeEditor) {
			content = _content;
			await tick();

			const res = await codeEditor.formatPythonCodeHandler();
			await tick();

			content = _content;
			await tick();

			if (res) {
				console.log('Code formatted successfully');

				saveHandler();
			}
		}
	};
</script>

<div class=" flex flex-col justify-between w-full overflow-y-auto h-full">
	<div class="mx-auto w-full md:px-0 h-full">
		<form
			bind:this={formElement}
			class=" flex flex-col max-h-[100dvh] h-full"
			on:submit|preventDefault={() => {
				if (edit) {
					submitHandler();
				} else {
					showConfirm = true;
				}
			}}
		>
			<div class="flex flex-col flex-1 overflow-auto h-0 rounded-lg">
				<div class="w-full mb-4 flex flex-col gap-1.5 px-1">
					<div class="flex w-full items-center gap-2">
						<Tooltip content={$i18n.t('Back')}>
							<button
								class="shrink-0 p-1.5 rounded-xl text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-800 transition-all duration-150"
								aria-label={$i18n.t('Back')}
								on:click={() => {
									goto(backHref);
								}}
								type="button"
							>
								<ChevronLeft strokeWidth="2.5" />
							</button>
						</Tooltip>

						<div class="flex-1 min-w-0">
							<Tooltip content={$i18n.t('e.g. 预报员的思路')} placement="top-start">
								<input
									class="w-full text-2xl font-semibold bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600 tracking-tight"
									type="text"
									placeholder={$i18n.t('Tool Name')}
									aria-label={$i18n.t('Tool Name')}
									bind:value={name}
									required
								/>
							</Tooltip>
						</div>

					</div>

					<div class="flex items-center gap-2">
						<div class="shrink-0 p-1.5 invisible">
							<ChevronLeft strokeWidth="2.5" />
						</div>

						<div class="flex-1 min-w-0 flex gap-3 items-center">
							{#if edit}
								<div class="shrink-0 text-xs font-mono text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
									{id}
								</div>
							{:else}
								<Tooltip
									className="shrink-0"
									content={$i18n.t('e.g. forecaster_toolkit')}
									placement="top-start"
								>
									<input
										class="w-40 text-xs font-mono text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 outline-hidden rounded-md px-2 py-1 focus:border-blue-400 dark:focus:border-blue-500 focus:ring-1 focus:ring-blue-400/20 transition-all duration-150"
										type="text"
										placeholder={$i18n.t('Tool ID')}
										aria-label={$i18n.t('Tool ID')}
										bind:value={id}
										required
										disabled={edit}
									/>
								</Tooltip>
							{/if}

							<div class="h-4 w-px bg-gray-200 dark:bg-gray-700" />

							<Tooltip
								className="flex-1 min-w-0"
								content={$i18n.t('e.g. 辅助预报员进行天气分析和预报决策')}
								placement="top-start"
							>
								<input
									class="w-full text-sm text-gray-600 dark:text-gray-400 bg-transparent outline-hidden placeholder:text-gray-300 dark:placeholder:text-gray-600"
									type="text"
									placeholder={$i18n.t('Tool Description')}
									aria-label={$i18n.t('Tool Description')}
									bind:value={meta.description}
									required
								/>
							</Tooltip>
						</div>
					</div>
				</div>

				<div class="mb-2 flex-1 overflow-auto h-0 rounded-lg">
					<CodeEditor
						bind:this={codeEditor}
						value={content}
						lang="python"
						{boilerplate}
						onChange={(e) => {
							_content = e;
						}}
						onSave={async () => {
							if (formElement) {
								formElement.requestSubmit();
							}
						}}
					/>
				</div>

				<div class="px-1 pb-3 flex items-center justify-between">
					<div class="flex items-center gap-2 text-xs text-gray-400 dark:text-gray-500">
						{#if edit && id}
							<span class="font-mono">{id}</span>
						{/if}
					</div>

					<button
						class="inline-flex items-center gap-2 px-5 py-2 text-sm font-medium bg-black hover:bg-gray-800 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition-all duration-150 rounded-xl shadow-sm hover:shadow active:scale-[0.98]"
						type="submit"
						disabled={loading}
					>
						{#if loading}
							<Spinner className="size-4" />
						{/if}
						{$i18n.t(edit ? 'Save' : 'Save & Create')}
					</button>
				</div>
			</div>
		</form>
	</div>
</div>

<ConfirmDialog
	bind:show={showConfirm}
	on:confirm={() => {
		submitHandler();
	}}
>
	<div class="text-sm text-gray-500">
		<div class=" bg-yellow-500/20 text-yellow-700 dark:text-yellow-200 rounded-lg px-4 py-3">
			<div>{$i18n.t('Please carefully review the following warnings:')}</div>

			<ul class=" mt-1 list-disc pl-4 text-xs">
				<li>
					{$i18n.t('Tools have a function calling system that allows arbitrary code execution.')}
				</li>
				<li>{$i18n.t('Do not install tools from sources you do not fully trust.')}</li>
			</ul>
		</div>

		<div class="my-3">
			{$i18n.t(
				'I acknowledge that I have read and I understand the implications of my action. I am aware of the risks associated with executing arbitrary code and I have verified the trustworthiness of the source.'
			)}
		</div>
	</div>
</ConfirmDialog>
